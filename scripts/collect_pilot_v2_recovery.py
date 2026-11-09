"""One prospective GPT/provider recovery, retaining every original A observation.

This coordinator has a new protocol/source/roster binding and the same ledger.
The inherited classifier is deliberately unchanged: new physical trace records
retain its legacy ``pilot_v2_stage_A`` phase string; their protocol hash is R1.
R1 membership, physical provenance and reuse are declared by the separate roster,
reuse mapping and R1 results header. No first physical trace is rewritten.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from pilot_v2.runner import PilotV2Runner, corpus_tasks, immutable, require
from resumption.runner import Runner, Settings, read_json, sha, utcnow
from stage0.config import parse_env
from stage0.runner import StopRun, encode, estimate

SCRIPT = "scripts/collect_pilot_v2_recovery.py"
STATUS = "prospective_frozen_provider_recovery"
PHASE = "pilot_v2_provider_recovery_R1"
GPT = "openai/gpt-oss-20b"
DEEPSEEK = "deepseek/deepseek-v4.1-flash"
ROUTES = {GPT: "AkashML", DEEPSEEK: "BytePlus"}


class RecoveryRunner(PilotV2Runner):
    def __init__(self, settings, protocol_path, corpus_path, transport=None, *, project=PROJECT,
                 execute=False, fixture_verifier=None):
        self.project = Path(project).resolve(strict=True)
        # The inherited paid writer uses scope.relative_to(state) after reserving.
        # Resolve aliases (including Windows 8.3 paths) before any binding/reserve.
        settings.state = settings.state.resolve(strict=True)
        self.protocol_path, self.corpus_path = Path(protocol_path), Path(corpus_path)
        protocol_bytes, corpus_bytes = self.protocol_path.read_bytes(), self.corpus_path.read_bytes()
        self.protocol, self.corpus = json.loads(protocol_bytes), json.loads(corpus_bytes)
        p, r = self.protocol, self.protocol["recovery"]
        require(p.get("schema_version") == 1 and p.get("status") == STATUS,
                "Recovery protocol is not prospectively finalized")
        require(r.get("condition") == "R1" and r.get("new_model") == GPT
                and r.get("new_provider") == "AkashML" and r.get("reused_model") == DEEPSEEK
                and r.get("new_calls") == 96 and r.get("reused_records") == 96
                and r.get("max_recovery_conditions") == 1,
                "Only one fixed all-96-cell provider recovery is authorized")
        self.parent_scope = (settings.state / r["parent_scope"]).resolve(strict=True)
        require(self.parent_scope.parent == (settings.state / "pilot-v2").resolve(strict=True),
                "Recovery parent must be the original shared-state pilot-v2 scope")
        self.a_protocol = read_json(self.parent_scope / "protocol.json")
        self.a_results = read_json(self.parent_scope / "results.json")
        self.a_plan = read_json(self.parent_scope / "dispatch-plan.json")
        self.a_inventory = read_json(self.parent_scope / "source-inventory.json")
        decision_path = (self.project / r["decision_path"]).resolve(strict=True)
        require(decision_path.is_relative_to(self.project), "Recovery decision must be project-owned")
        self.decision_path = decision_path
        decision = read_json(decision_path)
        require(sha(decision_path.read_bytes()) == r["decision_sha256"]
                and decision.get("status") == "design_recovery_condition_before_class_tally"
                and decision.get("original_condition_sha256") == r["parent_protocol_sha256"]
                and decision.get("original_results_sha256") == r["parent_results_sha256"],
                "Recovery decision does not bind the closed original A")
        require(sha((self.project / SCRIPT).read_bytes()) == r["collector_sha256"],
                "Recovery collector differs from prospective protocol")
        self._validate_contract(decision)
        self.model_specs = {row["model"]: row for row in p["models"]}
        self.launch_amount = Decimal(p["parent"]["launch_charged_or_reserved_rub"])
        self.stage_ceiling = Decimal(p["budget"]["absolute_stage_ceiling_rub"])
        expected_state = (self.project / p["budget"]["shared_state"]).resolve(strict=True)
        require(settings.state.resolve(strict=True) == expected_state and settings.cap == Decimal(3000),
                "Recovery must retain the original shared state and total cap")
        deadline = p["generation"]["dispatch_deadline_utc"]
        require(datetime.fromisoformat(deadline.replace("Z", "+00:00")) <=
                datetime.fromisoformat(read_json(expected_state / "dispatch-window.json")["deadline"].replace("Z", "+00:00")),
                "Recovery cannot extend the original dispatch deadline")
        settings.deadline, settings.timeout, settings.concurrency = deadline, 180, 3
        require(settings.temperature == .7 and settings.top_p == .95 and settings.seed == 42,
                "Recovery sampling must remain unchanged")
        self.scope = expected_state / "pilot-v2-recovery" / sha(protocol_bytes)
        self.execute_enabled, self.preflight_ready, self.active_cost_plan_sha256 = execute, False, None
        require(fixture_verifier is None or transport is not None and p.get("synthetic_fixture") is True,
                "A live recovery cannot replace the independent task verifier")
        self.fixture_verifier = fixture_verifier
        Runner.__init__(self, settings, transport)
        self.protocol_digest, self.tasks_digest = sha(protocol_bytes), sha(corpus_bytes)
        self.tasks, ordered = corpus_tasks(self.corpus)
        self.task_lookup = {task["task_id"]: task for task in self.tasks}
        self._verify_parent()
        with self.locked():
            registry = expected_state / "pilot-v2-recovery" / "condition-R1.json"
            self.recovery_registry = {"schema_version": 1, "condition": "R1", "protocol_sha256": self.protocol_digest,
                                      "decision_sha256": r["decision_sha256"],
                                      "parent_protocol_sha256": r["parent_protocol_sha256"]}
            immutable(registry, encode(self.recovery_registry))
            self.scope.mkdir(parents=True, exist_ok=True)
            immutable(self.scope / "protocol.json", protocol_bytes)
            immutable(self.scope / "corpus.json", corpus_bytes)
            launch_path = self.scope / "ledger-launch.json"
            if not launch_path.exists():
                require(sha(self.ledger_path.read_bytes()) == p["parent"]["launch_ledger_sha256"],
                        "Shared ledger changed before recovery binding")
                immutable(launch_path, self.ledger_path.read_bytes())
            self.launch_rows = read_json(launch_path)
            require(sha(launch_path.read_bytes()) == p["parent"]["launch_ledger_sha256"]
                    and len(self.launch_rows) == p["parent"]["launch_ledger_rows"]
                    and sum((Decimal(row["charged_or_reserved_rub"]) for row in self.launch_rows), Decimal(0)) == self.launch_amount,
                    "Recovery launch ledger binding changed")
            self._verify_original_a()
            self._freeze_v2_sources()
            generated = super()._make_plan(ordered)
            old = {self.key(cell): cell for cell in self.a_plan["cells"]}
            mixed = []
            for cell in generated["cells"]:
                previous = old[self.key(cell)]
                require(cell["seed"] == previous["seed"], "Recovery changed an original task sampling seed")
                mixed.append(previous if cell["model"] == DEEPSEEK else cell)
            self.plan = {**generated, "phase": PHASE, "new_calls": 96, "reused_records": 96,
                         "physical_record_phase_policy": "Inherited classifier phase is legacy; protocol SHA and R1 mapping define membership",
                         "cells": mixed}
            self.new_cells = [cell for cell in mixed if cell["model"] == GPT]
            require(len(self.new_cells) == 96 and len({cell["call_id"] for cell in mixed}) == 192,
                    "Recovery physical roster is not 96 reused plus 96 new unique cells")
            immutable(self.scope / "dispatch-plan.json", encode(self.plan))
            self.reuse_mapping = self._reuse_mapping()
            immutable(self.scope / "reuse-mapping.json", encode(self.reuse_mapping))

    @staticmethod
    def key(cell):
        return cell["task_id"], cell["model"], cell["output_budget_tokens"], cell.get("sample_index", 0)

    def _validate_contract(self, decision):
        p, a, r = self.protocol, self.a_protocol, self.protocol["recovery"]
        for field in ("tasks", "measurement", "stage_A", "future_study", "statistical_plan", "planning_scenarios"):
            require(p.get(field) == a.get(field), "Recovery changed original scientific contract: " + field)
        generation = {key: value for key, value in p["generation"].items() if key != "new_calls_max"}
        require(generation == a["generation"] and p["generation"].get("new_calls_max") == 96,
                "Recovery changed fixed sampling, roster, operational stop or deadline")
        require(p["budget"] == a["budget"], "Recovery cannot reset or increase the original stage budget")
        require(p["tasks"]["file_sha256"] == sha(self.corpus_path.read_bytes()), "Recovery corpus changed")
        specs = {row["model"]: row for row in p["models"]}
        originals = {row["model"]: row for row in a["models"]}
        require(len(p["models"]) == 2 and {model: spec["provider"] for model, spec in specs.items()} == ROUTES
                and specs[DEEPSEEK] == originals[DEEPSEEK], "Recovery route or reused model changed")
        route = decision["next_condition"]
        require(all(specs[GPT].get(key) == route.get(key) for key in
                    ("model", "provider", "parent_admission_call_id", "parent_request_sha256", "parent_response_sha256")),
                "Recovery GPT admission differs from pre-tally decision")
        require(all(p["parent"][key] == a["parent"][key] for key in ("protocol_sha256", "source_inventory_sha256")),
                "Recovery inherited parent changed")
        require(Decimal(p["parent"]["launch_charged_or_reserved_rub"]) ==
                Decimal(decision["budget"]["charged_or_reserved_before_recovery"]),
                "Recovery launch amount differs from closed-A decision")

    def _sources(self):
        sources = {name: (self.project / name).read_bytes() for name in self.a_inventory["files"]}
        sources[SCRIPT] = (self.project / SCRIPT).read_bytes()
        return dict(sorted(sources.items()))

    def _verify_original_a(self):
        r = self.protocol["recovery"]
        for filename, field in (("protocol.json", "parent_protocol_sha256"), ("results.json", "parent_results_sha256"),
                                ("dispatch-plan.json", "parent_dispatch_plan_sha256"),
                                ("source-inventory.json", "parent_source_inventory_sha256")):
            require(sha((self.parent_scope / filename).read_bytes()) == r[field], "Original A artifact changed: " + filename)
        for name, digest in self.a_inventory["files"].items():
            require(sha((self.project / name).read_bytes()) == digest
                    and sha((self.parent_scope / "source" / name).read_bytes()) == digest,
                    "Original frozen A source changed")
        rows, cells = self.a_results["records"], self.a_plan["cells"]
        require(len(rows) == len(cells) == 192 and self.a_results.get("all_planned_cells") == 192
                and len({self.key(row) for row in rows}) == 192
                and {self.key(row) for row in rows} == {self.key(cell) for cell in cells},
                "Original A does not retain its full fixed roster")
        planned = {self.key(cell): cell for cell in cells}
        call_ids = {cell["call_id"] for cell in cells}
        intent_dir = self.parent_scope / "intents"
        require(all(path.stem in call_ids for path in intent_dir.glob("*.json")),
                "Unmapped original A intent blocks provider recovery")
        ledger = self._read_retained_ledger()
        ledger_ids = {row["id"] for row in ledger.rows}
        attempted_gpt = []
        for row in rows:
            cell = planned[self.key(row)]
            require(row["trace_id"] == cell["call_id"], "Original A physical call identity changed")
            directory = self.calls / cell["call_id"]
            intent = self.parent_scope / "intents" / (cell["call_id"] + ".json")
            require(row.get("request_state") != "unknown"
                    and row.get("status") not in ("unknown", "unresolved_attempt", "unresolved_intent"),
                    "Any unknown original A attempt blocks provider recovery")
            if row.get("attempted") is False:
                require(row["model"] == GPT and row.get("status") == "not_dispatched"
                        and not directory.exists() and not intent.exists(),
                        "Original unsent A row has an underlying attempt")
                continue
            require(row.get("attempted") is True and directory.is_dir(), "Original A missing physical observation")
            reservation, result = read_json(directory / "reservation.json"), read_json(directory / "result.json")
            response_bytes = (directory / "response.json").read_bytes()
            response = json.loads(response_bytes)
            request_bytes = (directory / "request.json").read_bytes()
            trace = read_json(directory / "trace.json")
            require(response.get("http_status") is not None and not response.get("network_error")
                    and result.get("response") == response and result.get("response_sha256") == sha(response_bytes)
                    and row.get("response_sha256") == sha(response_bytes)
                    and result.get("request_sha256") == reservation.get("request_sha256") == sha(request_bytes)
                    and row.get("request_sha256") == sha(request_bytes) == cell["request_sha256"]
                    and result.get("reservation_id") == reservation.get("reservation_id") == row.get("reservation_id")
                    and reservation.get("reservation_id") in ledger_ids
                    and result.get("protocol_sha256") == r["parent_protocol_sha256"]
                    and result.get("source_inventory_sha256") == r["parent_source_inventory_sha256"]
                    and {k: v for k, v in trace.items() if k != "reused_record_without_resend"} ==
                        {k: v for k, v in row.items() if k != "reused_record_without_resend"},
                    "Original A raw observation/ledger/record binding changed")
            if row["model"] == GPT:
                error = response.get("json", {}).get("error")
                code = error.get("code") if isinstance(error, dict) else None
                require(response["http_status"] == 503 or str(code) == "503",
                        "Original attempted GPT was not the declared known 503 failure")
                attempted_gpt.append(row)
        require(len(attempted_gpt) == 2 and sum(row["model"] == DEEPSEEK and row.get("attempted") is True for row in rows) == 96,
                "Recovery requires the declared two known GPT503 and all96 retained DeepSeek observations")

    def _reuse_mapping(self):
        rows = {self.key(row): row for row in self.a_results["records"]}
        return {"schema_version": 1, "condition": "R1", "parent_results_sha256": self.protocol["recovery"]["parent_results_sha256"],
                "independent_roots": 24, "reused_records": [
                    {"task_id": cell["task_id"], "root_id": cell["root_id"], "model": DEEPSEEK,
                     "output_budget_tokens": cell["output_budget_tokens"], "trace_id": cell["call_id"],
                     "record_sha256": sha(encode(rows[self.key(cell)])),
                     "request_sha256": rows[self.key(cell)]["request_sha256"],
                     "response_sha256": rows[self.key(cell)]["response_sha256"],
                     "source_inventory_sha256": rows[self.key(cell)]["source_inventory_sha256"]}
                    for cell in self.plan["cells"] if cell["model"] == DEEPSEEK],
                "new_records": [{"trace_id": cell["call_id"], "task_id": cell["task_id"], "root_id": cell["root_id"],
                                 "output_budget_tokens": cell["output_budget_tokens"], "provider": "AkashML",
                                 "seed": cell["seed"], "parent_trace_id": rows[self.key(cell)]["trace_id"],
                                 "parent_condition_id": rows[self.key(cell)]["condition_id"],
                                 "parent_status": rows[self.key(cell)]["status"],
                                 "parent_response_sha256": rows[self.key(cell)].get("response_sha256")}
                                for cell in self.new_cells]}

    def _check_sources(self):
        super()._check_sources()
        require(sha(self.decision_path.read_bytes()) == self.protocol["recovery"]["decision_sha256"],
                "Prospective recovery decision changed")
        self._verify_original_a()
        require(read_json(self.scope / "reuse-mapping.json") == self.reuse_mapping,
                "Recovery reuse mapping changed")
        require(read_json(self.state / "pilot-v2-recovery" / "condition-R1.json") == self.recovery_registry,
                "The one permitted recovery condition registry changed")

    def paid_cell(self, cell):
        require(cell in self.new_cells and cell["model"] == GPT and cell["provider"] == "AkashML",
                "Recovery can dispatch only its new fixed GPT/AkashML cells")
        return super().paid_cell(cell)

    def preflight(self, refresh=True):
        # The retained DS96 already have their original quotes and costs. Never
        # quote them as new dispatch or credit their commitments against R1.
        self._check_sources()
        self.prices.clear()
        self.price_receipts.clear()
        rows = []
        for cell in self.new_cells:
            price = self.price(cell["model"], cell["provider"])
            attempted = (self.calls / cell["call_id"]).exists() or (self.scope / "intents" / (cell["call_id"] + ".json")).exists()
            rows.append({"call_id": cell["call_id"], "reservation_rub": str(estimate(self.body(cell), price)),
                         "previously_attempted": attempted, "prompt_rub_per_token": str(price[0]),
                         "completion_rub_per_token": str(price[1]),
                         "quote_receipt_sha256": self.price_receipts[(cell["model"], cell["provider"])]})
        remaining = sum((Decimal(row["reservation_rub"]) for row in rows if not row["previously_attempted"]), Decimal(0))
        with self.locked():
            ledger = self._check_shared_budget()
            plan = {"schema_version": 1, "phase": PHASE, "created_utc": utcnow(), "paid_requests": 0,
                    "dispatch_plan_sha256": sha(encode(self.plan)), "protocol_sha256": self.protocol_digest,
                    "source_inventory_sha256": self.source_inventory_digest, "cells": rows,
                    "new_calls": 96, "reused_records": 96,
                    "full_roster_reservation_rub": str(sum((Decimal(row["reservation_rub"]) for row in rows), Decimal(0))),
                    "remaining_new_reservation_rub": str(remaining), "launch_charged_or_reserved_rub": str(self.launch_amount),
                    "absolute_stage_ceiling_rub": str(self.stage_ceiling),
                    "full_roster_fits_stage_budget": ledger.committed + remaining <= self.stage_ceiling,
                    "current_shared_charged_or_reserved_rub": str(ledger.committed)}
            digest = sha(encode(plan))
            immutable(self.scope / "cost-plans" / (digest + ".json"), encode(plan))
            self.save(self.scope / "cost-plan.json", plan)
        self.preflight_ready, self.active_cost_plan_sha256 = True, digest
        return plan

    def run(self):
        require(self.execute_enabled, "Use --run --execute for authorized recovery execution")
        self._check_sources()
        need_new = any(not (self.calls / cell["call_id"]).exists()
                       and not (self.scope / "intents" / (cell["call_id"] + ".json")).exists() for cell in self.new_cells)
        deadline = datetime.fromisoformat(self.settings.deadline.replace("Z", "+00:00"))
        if need_new and self.settings.key and datetime.now(timezone.utc) < deadline:
            with self.locked():
                current = self._read_retained_ledger().committed
            if current < min(self.stage_ceiling, self.settings.cap):
                self.preflight()
        records = {row["trace_id"]: row for row in self.a_results["records"] if row["model"] == DEEPSEEK}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self.execute_cell, cell): cell for cell in self.new_cells}
            for future in as_completed(futures):
                cell = futures[future]
                try:
                    records[cell["call_id"]] = future.result()
                except StopRun as exc:
                    reserved = (self.calls / cell["call_id"] / "reservation.json").exists()
                    intended = (self.scope / "intents" / (cell["call_id"] + ".json")).exists()
                    records[cell["call_id"]] = {**cell, "trace_id": cell["call_id"], "split": "development", "phase": PHASE,
                        "status": "unresolved_attempt" if reserved else "unresolved_intent" if intended else "not_dispatched",
                        "request_state": "unknown" if reserved or intended else "not_dispatched", "http_status": None,
                        "attempted": True if reserved else None if intended else False,
                        "correct": None, "gradable": False, "text": "", "stop_reason": str(exc)}
        with self.locked():
            ledger = self._read_retained_ledger()
            output = {"schema_version": 1, "phase": PHASE, "condition": "R1", "protocol_sha256": self.protocol_digest,
                "corpus_sha256": self.tasks_digest, "source_inventory_sha256": self.source_inventory_digest,
                "dispatch_plan_sha256": sha(encode(self.plan)), "reuse_mapping_sha256": sha(encode(self.reuse_mapping)),
                "parent_results_sha256": self.protocol["recovery"]["parent_results_sha256"],
                "physical_record_phase_policy": self.plan["physical_record_phase_policy"],
                "records": [records[cell["call_id"]] for cell in self.plan["cells"]], "all_planned_cells": 192,
                "new_planned_calls": 96, "reused_records": 96, "independent_roots": 24,
                "charged_or_reserved_rub": str(ledger.committed), "E0": "not_passed",
                "scientific_validity": "not_assessed", "completed_utc": utcnow()}
            self.save(self.scope / "results.json", output)
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--dry-run", action="store_true")
    commands.add_argument("--preflight", action="store_true")
    commands.add_argument("--run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=PROJECT / ".research/resumption-2026-11-08-live")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.execute != args.run:
        parser.error("--run and --execute must be supplied together")
    try:
        values = {**(parse_env(args.env_file) if args.env_file else {}), **os.environ}
        require(values.get("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1") == "https://routerai.ru/api/v1",
                "Only the prescribed RouterAI endpoint is allowed")
        runner = RecoveryRunner(Settings(state=args.state, key=values.get("ROUTERAI_API_KEY", ""),
                                cap=Decimal(3000), collection_cap=Decimal(3000)), args.protocol, args.tasks,
                                execute=args.execute)
        if args.dry_run:
            output = {"dry_run": True, "paid_requests": 0, "planned_cells": 192, "new_calls": 96,
                      "reused_records": 96, "protocol_sha256": runner.protocol_digest,
                      "source_inventory_sha256": runner.source_inventory_digest, "scope": str(runner.scope)}
        else:
            output = runner.run() if args.run else runner.preflight()
            output = {key: value for key, value in output.items() if key not in ("records", "cells")}
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except StopRun as exc:
        print(json.dumps({"stopped": True, "reason": str(exc)}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
