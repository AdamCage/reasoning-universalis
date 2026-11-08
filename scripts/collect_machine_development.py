"""Finite machine-only role annotation with the existing shared budget journal.

No human reference, gold, E0 acceptance or scientific review is created. Every
physical vote, conditional vote and audit has a distinct predeclared identity.
Unknown calls are cached, never automatically resent or disguised as audits.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from resumption.runner import Runner, Settings, read_json, sha, utcnow, HISTORICAL_ARCHIVE, HISTORICAL_MEMBER, HISTORICAL_SHA
from scripts.pilot_v2_ledger_io_compat_v1 import CooperativeLedgerIOMixin, SOURCE_PATH, VERSION as IO_VERSION
from stage0.config import parse_env
from stage0.runner import Ledger, StopRun, encode, estimate
from stage0.traces import inspect_trace
from machine_development import annotation

SCRIPT = "scripts/collect_machine_development.py"
MODEL, PROVIDER = "deepseek/deepseek-v4.1-flash", "BytePlus"
STATUS = "prospective_frozen_machine_development"
KIND = "machine_development_annotation"


def require(condition, message):
    if not condition:
        raise StopRun(message)


def immutable(path, data):
    if path.exists():
        require(path.read_bytes() == data, "Machine annotation immutable artifact changed")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class MachineSettings(Settings):
    """New explicit 3300 RUB authorization; historical Settings stays frozen."""

    def __post_init__(self):
        requested_cap, requested_collection = Decimal(str(self.cap)), Decimal(str(self.collection_cap))
        require(requested_cap.is_finite() and 0 < requested_cap <= Decimal(3300)
                and requested_collection.is_finite() and 0 < requested_collection <= requested_cap,
                "Machine settings exceed the newly authorized 3300 RUB total")
        self.cap, self.collection_cap = min(requested_cap, Decimal(3000)), min(requested_collection, Decimal(3000))
        super().__post_init__()
        self.cap, self.collection_cap = requested_cap, requested_collection


class _MachineCore(Runner):
    def __init__(self, settings, protocol_path, transport=None, *, project=PROJECT, execute=False):
        self.project = Path(project).resolve(strict=True)
        settings.state = Path(settings.state).resolve(strict=True)
        self.protocol_path = Path(protocol_path).resolve(strict=True)
        protocol_bytes = self.protocol_path.read_bytes()
        self.protocol = p = read_json(self.protocol_path)
        g, allocation, budget, parent = (p[name] for name in ("generation", "allocation", "budget", "parent"))
        require(p.get("schema_version") == 1 and p.get("status") == STATUS, "Machine development protocol is not finalized")
        require(g.get("model") == MODEL and g.get("provider") == PROVIDER and g.get("temperature") == .7
                and g.get("top_p") == 1 and g.get("max_output_tokens") == 1024
                and g.get("request_timeout_seconds") == 120 and g.get("concurrency_max") == 3
                and g.get("reasoning_enabled") is False and g.get("automatic_retries") == 0,
                "Machine annotation parameters differ from the finite protocol")
        self.input_specs = {"items": p["inputs"], "codebook": p["inputs"]["codebook"], "mapping": p["inputs"]["mapping"],
                            "annotation_config": p["annotation_config"]}
        for label, field in (("route_metadata", "route_receipt"), ("license_receipt", "license_receipt")):
            if field in p.get("metadata", {}):
                self.input_specs[label] = {"path": p["metadata"][field], "file_sha256": p["metadata"][field + "_sha256"]}
        self.input_paths, self.input_bytes = {}, {}
        for name, spec in self.input_specs.items():
            relative = Path(spec["path"])
            require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe machine input path")
            path = (self.project / relative).resolve(strict=True)
            require(path.is_relative_to(self.project), "Machine input is outside project")
            data = path.read_bytes()
            require(sha(data) == spec["file_sha256"], "Machine input does not match its prospective hash")
            self.input_paths[name], self.input_bytes[name] = path, data
        self.input_document = json.loads(self.input_bytes["items"])
        self.items = self.input_document["items"]
        self.codebook, self.mapping = (json.loads(self.input_bytes[name]) for name in ("codebook", "mapping"))
        self.config = json.loads(self.input_bytes["annotation_config"])
        require(p["annotation_config"]["path"] == "design/ANNOTATION_CONFIG.json", "Use the existing fixed annotation configuration")
        require(all((self.project / name).is_file() and sha((self.project / name).read_bytes()) == digest
                    for name, digest in self.codebook["source_sha256"].items()), "Machine codebook source documents changed")
        self.item_lookup = {item["item_id"]: item for item in self.items}
        n = len(self.items)
        require(p.get("synthetic_fixture") is True or n == 200, "The newly funded live condition requires all 200 prepared items")
        self.audit_ids = list(annotation.audit_item_ids(self.items))
        audit_n = math.ceil(.1 * n)
        require(n in (*range(24, 193, 24), 200) and n == len(self.item_lookup) == p["inputs"]["items"]
                and p["inputs"]["roots"] == 24, "Machine development requires a fixed balanced 24-root allocation")
        require(allocation.get("panel_size") == 5 and allocation.get("majority_required") == 3
                and allocation.get("maximum_rounds") == 2 and allocation.get("first_round_calls") == 5 * n
                and allocation.get("conditional_second_round_calls") == 5 * n
                and allocation.get("audit_items") == audit_n and allocation.get("audit_calls") == 5 * audit_n
                and allocation.get("maximum_calls") == 10 * n + 5 * audit_n <= 2100,
                "Machine vote/conditional/audit roster differs from the prospective allocation")
        require(len(self.audit_ids) == audit_n and len(set(self.audit_ids)) == audit_n
                and set(self.audit_ids) <= set(self.item_lookup)
                and self.input_document.get("audit_item_ids") == self.audit_ids,
                "Same-seed audit selection is not fixed before votes")
        roots = [self.mapping["items"][item_id]["root_id"] for item_id in self.item_lookup]
        expected_counts = [8] * 16 + [9] * 8 if n == 200 else [n // 24] * 24
        require(len(set(roots)) == 24 and sorted(Counter(roots).values()) == expected_counts,
                "Machine input is not balanced over its 24 original roots")
        require(self.config["panel_size"] == 5 and self.config["majority_required"] == 3
                and self.config["maximum_rounds"] == 2 and tuple(map(tuple, self.config["seed_schedule"])) == tuple(annotation.SEEDS),
                "Existing fixed annotation seeds or vote rules changed")
        self.launch_amount = Decimal(parent["launch_charged_or_reserved_rub"])
        self.stage_ceiling = Decimal(budget["absolute_stage_ceiling_rub"])
        require(settings.cap == Decimal(budget["cap_total_rub"]) == Decimal(3300)
                and Decimal(budget["stage_additional_cap_rub"]) == Decimal(2400)
                and self.stage_ceiling == self.launch_amount + Decimal(2400) <= settings.cap,
                "Machine annotation cannot reset or exceed the declared global/additional budget")
        expected_state = (self.project / budget["shared_state"]).resolve(strict=True)
        require(expected_state == settings.state and (expected_state / "ledger.json").is_file(), "Use the existing shared state and ledger")
        if not p.get("synthetic_fixture"):
            require(parent["launch_ledger_rows"] == 984 and self.launch_amount == Decimal("823.5589067445220"),
                    "Machine annotation must retain the closed 984-row pilot ledger")
        require(transport is not None or not p.get("synthetic_fixture"), "Synthetic fixtures need an explicit fake transport")
        deadline = datetime.fromisoformat(g["dispatch_deadline_utc"].replace("Z", "+00:00"))
        require(deadline.tzinfo is not None, "Machine dispatch deadline requires timezone")
        settings.deadline, settings.timeout, settings.concurrency = g["dispatch_deadline_utc"], 120, 3
        self.scope = expected_state / "machine-development" / sha(protocol_bytes)
        self.execute_enabled, self.preflight_ready, self.active_cost_plan_sha256 = execute, False, None
        super().__init__(settings, transport)
        self.protocol_digest = sha(protocol_bytes)
        self.items_digest = sha(self.input_bytes["items"])
        self.rendered = {item_id: annotation.render_item(item, self.codebook,
                         max_input_bytes=g.get("maximum_input_utf8_bytes")) for item_id, item in self.item_lookup.items()}
        self._verify_parent()
        with self.locked():
            self.scope.mkdir(parents=True, exist_ok=True)
            immutable(self.scope / "protocol.json", protocol_bytes)
            for name, data in self.input_bytes.items():
                immutable(self.scope / (name + ".json"), data)
            launch_path = self.scope / "ledger-launch.json"
            if not launch_path.exists():
                data = self.ledger_path.read_bytes()
                require(sha(data) == parent["launch_ledger_sha256"], "Shared ledger changed before machine annotation binding")
                immutable(launch_path, data)
            self.launch_rows = read_json(launch_path)
            require(sha(launch_path.read_bytes()) == parent["launch_ledger_sha256"]
                    and len(self.launch_rows) == parent["launch_ledger_rows"]
                    and sum((Decimal(row["charged_or_reserved_rub"]) for row in self.launch_rows), Decimal(0)) == self.launch_amount,
                    "Machine launch ledger does not match retained obligations")
            self._freeze_sources()
            self.plan = self._make_plan()
            self.cells = {cell["call_id"]: cell for cell in self.plan["cells"]}
            self._reservation_calls, self._financial_cache = {}, {}
            self._index_reservations()
            immutable(self.scope / "dispatch-plan.json", encode(self.plan))
            immutable(self.scope / "dispatch-window.json", encode({"deadline": settings.deadline, "protocol_sha256": self.protocol_digest,
                       "scope": "new explicit machine-only task; original pilot windows unchanged"}))
            self._read_retained_ledger()

    def _initialize_ledger(self):
        require(self.ledger_path.is_file(), "Machine annotation cannot create a fresh ledger")
        with zipfile.ZipFile(HISTORICAL_ARCHIVE) as archive:
            original = archive.read(HISTORICAL_MEMBER)
        require(sha(original) == HISTORICAL_SHA, "Historical ledger source changed")
        self.historical_rows = json.loads(original)
        self._read_retained_ledger()

    def _read_retained_ledger(self):
        ledger = Ledger(self.ledger_path, self.settings.cap)
        require(ledger.rows[:len(self.historical_rows)] == self.historical_rows, "Historical ledger prefix changed")
        if hasattr(self, "launch_rows"):
            require(ledger.rows[:len(self.launch_rows)] == self.launch_rows, "Closed pilot ledger prefix changed")
        require(len({row["id"] for row in ledger.rows}) == len(ledger.rows), "Repeated ledger reservation ID")
        require(all(Decimal(row["charged_or_reserved_rub"]).is_finite()
                    and Decimal(row["charged_or_reserved_rub"]) >= 0 for row in ledger.rows), "Invalid retained budget obligation")
        for row in ledger.rows[len(getattr(self, "launch_rows", ledger.rows)):]:
            reserve, commitment = Decimal(row["reservation_rub"]), Decimal(row["charged_or_reserved_rub"])
            require(reserve.is_finite() and reserve > 0 and commitment >= reserve, "Machine reservation obligation was reduced")
            if row.get("reported_cost_rub") is not None:
                cost = Decimal(row["reported_cost_rub"])
                require(cost.is_finite() and cost >= 0 and commitment >= cost, "Machine reported cost obligation was reduced")
        if hasattr(self, "_reservation_calls"):
            for row in ledger.rows[len(self.launch_rows):]:
                if row["id"] not in self._reservation_calls:
                    self._index_reservations()
                require(row["id"] in self._reservation_calls, "Unmapped new shared-ledger reservation")
                self._verify_raw_accounting(self._reservation_calls[row["id"]], row)
        return ledger

    def _index_reservations(self):
        for cell in self.plan["cells"]:
            path = self.calls / cell["call_id"] / "reservation.json"
            if path.is_file():
                context = read_json(path)
                previous = self._reservation_calls.setdefault(context["reservation_id"], cell["call_id"])
                require(previous == cell["call_id"], "One reservation was attached to different machine attempts")

    @staticmethod
    def _accounting_response(response):
        if not isinstance(response.get("json"), dict):
            return {**response, "json": {}}, "nonobject_payload_cost_unavailable_reservation_retained"
        if response["json"].get("usage") is not None and not isinstance(response["json"]["usage"], dict):
            return {**response, "json": {**response["json"], "usage": {}}}, "usage_shape_normalized_for_accounting_raw_preserved"
        return response, "original_object"

    def _verify_raw_accounting(self, call_id, row):
        directory = self.calls / call_id
        context_path, result_path, response_path = (directory / name for name in ("reservation.json", "result.json", "response.json"))
        if not result_path.is_file():
            require(row["state"] == "pending", "Known finalized machine ledger row is missing its raw result")
            return
        signature = tuple((path.stat().st_size, path.stat().st_mtime_ns) for path in (context_path, result_path, response_path))
        cached = self._financial_cache.get(call_id)
        if cached is None or cached[0] != signature:
            context, result, response = read_json(context_path), read_json(result_path), read_json(response_path)
            require(context["call_id"] == result["call_id"] == call_id and result["reservation_id"] == context["reservation_id"]
                    and context["protocol_sha256"] == self.protocol_digest
                    and result["response_sha256"] == sha(response_path.read_bytes()) and result["response"] == response,
                    "Known financial response/raw context binding changed")
            accounting, scope = self._accounting_response(response)
            payload = accounting["json"]
            cost = (payload.get("usage") or {}).get("cost")
            if cost is None:
                cost = payload.get("cost")
            parsed, error = None, False
            if cost is not None:
                try:
                    parsed = Decimal(str(cost))
                    if not parsed.is_finite() or parsed < 0:
                        raise ValueError
                except Exception:
                    parsed, error = None, True
            proof = {"reservation_id": context["reservation_id"], "reserve": Decimal(context["reservation_rub"]),
                     "reported": str(parsed) if parsed is not None else None, "cost": parsed,
                     "parse_error": error, "state": "finished" if response.get("http_status") is not None else "unknown"}
            self._financial_cache[call_id] = signature, proof
        else:
            proof = cached[1]
        require(row["id"] == proof["reservation_id"] and Decimal(row["reservation_rub"]) == proof["reserve"]
                and row.get("reported_cost_rub") == proof["reported"] and row["state"] == proof["state"]
                and bool(row.get("cost_parse_error", False)) == proof["parse_error"]
                and Decimal(row["charged_or_reserved_rub"]) >= max(proof["reserve"], proof["cost"] or Decimal(0)),
                "Retained machine ledger accounting differs from the original known raw cost")

    def _check_shared_budget(self):
        ledger = self._read_retained_ledger()
        require(ledger.committed <= self.stage_ceiling and ledger.committed <= self.settings.cap,
                "Machine annotation global/additional budget exhausted")
        return ledger

    def _verify_parent(self):
        parent = self.protocol["parent"]
        require(sha((self.state / "protocol.json").read_bytes()) == parent["protocol_sha256"]
                and sha((self.state / "source-inventory.json").read_bytes()) == parent["source_inventory_sha256"],
                "Inherited pilot protocol/source proof changed")
        directory = self.calls / parent["admission_call_id"]
        request_bytes, response_bytes = (directory / "request.json").read_bytes(), (directory / "response.json").read_bytes()
        request, response = json.loads(request_bytes), json.loads(response_bytes)
        context, result = read_json(directory / "reservation.json"), read_json(directory / "result.json")
        ledger_ids = {row["id"] for row in self._read_retained_ledger().rows}
        require(sha(request_bytes) == parent["admission_request_sha256"] == context["request_sha256"]
                and sha(response_bytes) == parent["admission_response_sha256"] == result["response_sha256"]
                and result["response"] == response and result["reservation_id"] == context["reservation_id"]
                and context["reservation_id"] in ledger_ids and result["protocol_sha256"] == parent["protocol_sha256"],
                "Machine parent admission is not bound to the retained raw call and ledger")
        payload = response.get("json", {})
        require(request.get("model") == payload.get("model") == MODEL and payload.get("provider") == PROVIDER
                and response.get("http_status") == 200 and payload.get("error") is None
                and inspect_trace(payload)["status"] == "visible_trace_candidate", "Parent model/provider admission changed")

    def _sources(self):
        old = read_json(self.state / "source-inventory.json")["files"]
        required = {SCRIPT, SOURCE_PATH, "scripts/prepare_machine_development.py",
                    "stage2/__init__.py", "stage2/annotation.py", "stage2/observations.py",
                    "stage0/__init__.py", "stage0/tasks.py",
                    "measurement/__init__.py", "measurement/core.py", "measurement/lexical.py",
                    "design/ANNOTATION_CONFIG.json", "design/ANNOTATION_RESPONSE.schema.json",
                    "design/ANNOTATION_PROTOCOL.md", "design/prompts/segment-role-v1.md"}
        required |= set(old)
        required |= {path.relative_to(self.project).as_posix() for path in (self.project / "machine_development").glob("*.py")}
        sources = {name: (self.project / name).read_bytes() for name in sorted(required)}
        require("machine_development/annotation.py" in sources, "Machine annotation module is absent")
        require(all(sha(sources[name]) == digest for name, digest in old.items()), "Inherited frozen source bytes changed")
        return sources

    def _freeze_sources(self):
        sources = self._sources()
        inventory = {"schema_version": 1, "scope": "machine-only annotation sources/config plus exact inherited closure",
                     "files": {name: sha(data) for name, data in sources.items()}}
        digest = sha(encode(inventory))
        expected = self.protocol.get("source_freeze", {}).get("expected_source_inventory_sha256")
        require(expected == digest or expected is None and self.protocol.get("synthetic_fixture") is True,
                "Machine source differs from the prospective pre-binding inventory")
        for name, data in sources.items():
            require(not self.settings.key or self.settings.key.encode() not in data, "Credential literal found in source")
            immutable(self.scope / "source" / name, data)
        immutable(self.scope / "source-inventory.json", encode(inventory))
        self.source_inventory_digest = digest
        expected_io = {"version": IO_VERSION, "path": SOURCE_PATH, "sha256": inventory["files"][SOURCE_PATH]}
        require(self.protocol["execution_io_compatibility"] == expected_io, "Prospective I/O compatibility binding differs")

    def _check_sources(self):
        require(sha(self.protocol_path.read_bytes()) == self.protocol_digest, "Machine protocol changed after binding")
        require(all(path.read_bytes() == self.input_bytes[name] for name, path in self.input_paths.items()), "Machine inputs/codebook/config changed after binding")
        inventory = read_json(self.scope / "source-inventory.json")
        require(sha((self.scope / "source-inventory.json").read_bytes()) == self.source_inventory_digest
                and {name: sha(data) for name, data in self._sources().items()} == inventory["files"],
                "Machine code/config changed after freeze")
        for name, digest in inventory["files"].items():
            require(sha((self.scope / "source" / name).read_bytes()) == digest, "Machine source snapshot changed")
        self._verify_parent()
        registry_path = self.state / "machine-development/condition-v1.json"
        if registry_path.exists():
            require(read_json(registry_path) == self._condition_registry(), "A different machine condition already owns this shared ledger")

    def _condition_registry(self):
        return {"schema_version": 1, "condition": "machine-development-v1", "protocol_sha256": self.protocol_digest,
                "source_inventory_sha256": self.source_inventory_digest, "items_sha256": self.items_digest,
                "launch_ledger_sha256": self.protocol["parent"]["launch_ledger_sha256"]}

    def body(self, cell):
        return {"model": MODEL, "messages": self.rendered[cell["item_id"]]["messages"],
                "max_tokens": 1024, "temperature": .7, "top_p": 1.0,
                "seed": annotation.SEEDS[cell["round_number"] - 1][cell["vote_index"]],
                "stream": False, "reasoning": {"enabled": False}, "include_reasoning": False,
                "provider": {"order": [PROVIDER], "allow_fallbacks": False}}

    def _make_plan(self):
        cells = []
        for item_id in sorted(self.item_lookup):
            for round_number, audit in ((1, False), (2, False), (1, True)):
                if audit and item_id not in self.audit_ids:
                    continue
                for vote_index in range(5):
                    identity = [item_id, round_number, vote_index, "audit" if audit else "primary"]
                    cell = {"item_id": item_id, "round_number": round_number, "vote_index": vote_index, "audit": audit,
                            "identity": identity, "seed": annotation.SEEDS[round_number - 1][vote_index],
                            "conditional": "first_panel_complete_without_majority" if round_number == 2 else
                                           "selected_first_panel_technically_complete" if audit else "always"}
                    cell["call_id"] = sha(encode({"kind": KIND, "identity": identity, "protocol": self.protocol_digest, "model": MODEL}))
                    cell["request_sha256"] = sha(encode(self.body(cell)))
                    cells.append(cell)
        require(len(cells) == self.protocol["allocation"]["maximum_calls"] and len({row["call_id"] for row in cells}) == len(cells),
                "Machine annotation prospective call roster differs")
        return {"schema_version": 1, "protocol_sha256": self.protocol_digest, "items_sha256": self.items_digest,
                "source_inventory_sha256": self.source_inventory_digest, "audit_item_ids": self.audit_ids,
                "cells": cells, "E0": "not_passed", "human_gold": "not_created"}

    def _metadata(self, path, name):
        response = self.transport(path, timeout=30)
        record = {"retrieved_at": utcnow(), "endpoint": path, "response": {key: value for key, value in response.items() if key != "headers"}}
        receipt = self.save(self.scope / "metadata" / (name + ".json"), record)
        immutable(self.scope / "metadata/history" / (receipt + ".json"), (self.scope / "metadata" / (name + ".json")).read_bytes())
        require(response.get("http_status") == 200 and not response.get("json", {}).get("error"), "Current machine quote is unavailable")
        return {**response, "metadata_receipt_sha256": receipt}

    def preflight(self):
        self._check_sources()
        self.prices.clear(); self.price_receipts.clear()
        price = self.price(MODEL, PROVIDER)
        rows = []
        for cell in self.plan["cells"]:
            amount = estimate(self.body(cell), price)
            attempted = (self.calls / cell["call_id"]).exists() or (self.scope / "intents" / (cell["call_id"] + ".json")).exists()
            rows.append({"call_id": cell["call_id"], "reservation_rub": str(amount), "previously_attempted": attempted,
                         "quote_receipt_sha256": self.price_receipts[(MODEL, PROVIDER)]})
        remaining = sum((Decimal(row["reservation_rub"]) for row in rows if not row["previously_attempted"]), Decimal(0))
        with self.locked():
            ledger = self._check_shared_budget()
            plan = {"schema_version": 1, "created_utc": utcnow(), "paid_requests": 0,
                    "protocol_sha256": self.protocol_digest, "source_inventory_sha256": self.source_inventory_digest,
                    "dispatch_plan_sha256": sha(encode(self.plan)), "cells": rows,
                    "maximum_calls": len(rows), "worst_case_reservation_rub": str(sum((Decimal(row["reservation_rub"]) for row in rows), Decimal(0))),
                    "remaining_new_reservation_rub": str(remaining), "current_shared_charged_or_reserved_rub": str(ledger.committed),
                    "absolute_stage_ceiling_rub": str(self.stage_ceiling),
                    "full_roster_fits_stage_budget": ledger.committed + remaining <= min(self.stage_ceiling, self.settings.cap)}
            digest = sha(encode(plan))
            immutable(self.scope / "cost-plans" / (digest + ".json"), encode(plan))
            self.save(self.scope / "cost-plan.json", plan)
        self.preflight_ready, self.active_cost_plan_sha256 = True, digest
        return plan

    def _cached(self, cell):
        directory = self.calls / cell["call_id"]
        if not directory.exists():
            require(not (self.scope / "intents" / (cell["call_id"] + ".json")).exists(), "Unfinalized machine intent cannot be retried")
            return None
        result = self._cached_call(directory, encode(self.body(cell)))
        require(result["kind"] == KIND and result["identity"] == cell["identity"]
                and result["protocol_sha256"] == self.protocol_digest and result["items_sha256"] == self.items_digest
                and result["source_inventory_sha256"] == self.source_inventory_digest
                and sha((directory / "response.json").read_bytes()) == result["response_sha256"]
                and read_json(directory / "response.json") == result["response"],
                "Cached machine response differs from its raw/source binding")
        context = read_json(directory / "reservation.json")
        require(all(result.get(key) == value for key, value in context.items()), "Machine cached reservation context differs")
        row = next((row for row in self._read_retained_ledger().rows if row["id"] == result["reservation_id"]), None)
        require(result["call_id"] == cell["call_id"] and result["request_sha256"] == cell["request_sha256"]
                and result["http_status"] == result["response"].get("http_status")
                and row is not None and Decimal(row["reservation_rub"]) == Decimal(context["reservation_rub"])
                and Decimal(row["charged_or_reserved_rub"]) >= Decimal(context["reservation_rub"])
                and row["state"] == ("finished" if result["http_status"] is not None else "unknown"),
                "Machine cached observation lost or changed its retained reserve/state")
        return result

    def paid_cell(self, cell):
        require(self.execute_enabled, "Machine collection requires explicit --execute")
        self._check_sources()
        require(self.cells.get(cell["call_id"]) == cell, "Machine cell is outside its fixed roster")
        require(not self.rendered[cell["item_id"]].get("oversized"), "oversized_unresolved: no annotation request sent")
        body = self.body(cell)
        require(sha(encode(body)) == cell["request_sha256"], "Machine request body changed")
        context_limit = self.protocol.get("metadata", {}).get("BytePlus_declared_context_length", 1048576)
        require(type(context_limit) is int and len(encode(body)) + 2048 + 1024 <= context_limit,
                "oversized_unresolved: conservative request/context bound exceeded")
        with self.locked():
            cached = self._cached(cell)
            if cached is not None:
                return cached
        require(self.preflight_ready and self.active_cost_plan_sha256 is not None
                and read_json(self.scope / "cost-plan.json")["full_roster_fits_stage_budget"] is True,
                "Fresh complete worst-case machine allocation quote must fit before dispatch")
        require(bool(self.settings.key), "ROUTERAI_API_KEY is not configured")
        self._deadline()
        price = self.price(MODEL, PROVIDER)
        amount = estimate(body, price)
        with self.locked():
            cached = self._cached(cell)
            if cached is not None:
                return cached
            self._deadline()
            ledger = self._check_shared_budget()
            self._condition_eligible(cell)
            failures = read_json(self.scope / "route-state.json") if (self.scope / "route-state.json").is_file() else {"operational_failure_calls": []}
            require(len(failures["operational_failure_calls"]) < self.protocol["generation"].get("operational_failure_limit_per_route", 2),
                    "Machine route stopped after two observed operational failures")
            require(ledger.committed + amount <= min(self.stage_ceiling, self.settings.cap), "Machine reservation exceeds the global/additional ceiling")
            immutable(self.state / "machine-development/condition-v1.json", encode(self._condition_registry()))
            intent = {"schema_version": 1, "cell": cell, "protocol_sha256": self.protocol_digest,
                      "source_inventory_sha256": self.source_inventory_digest, "items_sha256": self.items_digest}
            immutable(self.scope / "intents" / (cell["call_id"] + ".json"), encode(intent))
            directory = self.calls / cell["call_id"]
            directory.mkdir()
            request_digest = self.save(directory / "request.json", body)
            reservation = ledger.reserve(amount, "machine_development:annotation:" + MODEL)
            context = {"call_id": cell["call_id"], "kind": KIND, "identity": cell["identity"], "item_id": cell["item_id"],
                       "round_number": cell["round_number"], "vote_index": cell["vote_index"], "audit": cell["audit"],
                       "model": MODEL, "provider": PROVIDER, "seed_requested": cell["seed"], "seed_execution": "not_independently_confirmed",
                       "protocol_sha256": self.protocol_digest, "items_sha256": self.items_digest,
                       "source_inventory_sha256": self.source_inventory_digest, "request_sha256": request_digest,
                       "reservation_id": reservation["id"], "reservation_rub": str(amount),
                       "quote_receipt_sha256": self.price_receipts[(MODEL, PROVIDER)],
                       "quote_namespace": self.scope.relative_to(self.state).as_posix() + "/metadata/history",
                       "cost_plan_sha256": self.active_cost_plan_sha256,
                       "quoted_prompt_rub_per_token": str(price[0]), "quoted_completion_rub_per_token": str(price[1]),
                       "reserved_at": utcnow(), "automatic_retries": 0}
            self.save(directory / "reservation.json", context)
            self._reservation_calls[reservation["id"]] = cell["call_id"]
        try:
            response = self.transport("/chat/completions", key=self.settings.key, body=body, timeout=120)
        except Exception as exc:
            response = {"http_status": None, "json": {}, "network_error": type(exc).__name__}
        safe = {key: value for key, value in response.items() if key != "headers"}
        response_digest = self.save(directory / "response.json", safe)
        with self.locked():
            ledger = self._read_retained_ledger()
            row = next(row for row in ledger.rows if row["id"] == context["reservation_id"])
            accounting_safe, accounting_scope = self._accounting_response(safe)
            try:
                ledger.finish(row, accounting_safe)
            except StopRun:
                pass
            result = {**context, "response": safe, "response_sha256": response_digest, "http_status": safe.get("http_status"),
                      "completed_at": utcnow(), "ledger_sha256": sha(self.ledger_path.read_bytes()),
                      "accounting_payload_scope": accounting_scope,
                      "budget_overrun": ledger.committed > min(self.stage_ceiling, self.settings.cap)}
            self.save(directory / "result.json", result)
            if self._operational_failure(safe):
                self._record_operational_failure(cell["call_id"])
        return result

    @staticmethod
    def _operational_failure(response):
        payload = response.get("json", {})
        return not (response.get("http_status") == 200 and not response.get("network_error")
                    and not response.get("decode_error") and isinstance(payload, dict) and payload.get("error") is None
                    and payload.get("model") == MODEL and payload.get("provider") == PROVIDER)

    def _record_operational_failure(self, call_id):
        path = self.scope / "route-state.json"
        state = read_json(path) if path.is_file() else {"operational_failure_calls": []}
        if call_id not in state["operational_failure_calls"]:
            state["operational_failure_calls"].append(call_id)
            self.save(path, state)

    def _parsed(self, cell, result):
        response = result["response"]
        payload = response.get("json", {})
        base = {"call_id": cell["call_id"], "item_id": cell["item_id"], "round_number": cell["round_number"],
                "vote_index": cell["vote_index"], "audit": cell["audit"], "request_sha256": result["request_sha256"],
                "response_sha256": result["response_sha256"], "reservation_id": result["reservation_id"],
                "http_status": response.get("http_status"), "request_state": "unknown" if response.get("http_status") is None or response.get("network_error") else "finished"}
        base["operational_failure"] = self._operational_failure(response)
        choices = payload.get("choices") if isinstance(payload, dict) else None
        message = choices[0].get("message", {}) if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = message if isinstance(message, dict) else {}
        base.update(requested_reasoning_disabled=True,
                    returned_reasoning_present=bool(message.get("reasoning") or message.get("reasoning_content") or message.get("reasoning_details")),
                    effective_reasoning_mode="not_independently_confirmed")
        try:
            require(response.get("http_status") == 200 and not response.get("network_error") and not response.get("decode_error")
                    and payload.get("error") is None and payload.get("model") == MODEL and payload.get("provider") == PROVIDER,
                    "annotation_transport_or_identity_invalid")
            choices = payload.get("choices")
            require(type(choices) is list and len(choices) == 1 and choices[0].get("finish_reason") == "stop",
                    "annotation_output_not_complete")
            content = choices[0].get("message", {}).get("content")
            require(isinstance(content, str), "annotation_content_missing")
            vote = annotation.parse_response(content, self.item_lookup[cell["item_id"]])
            return {**base, "technical_status": "valid", "vote": vote, "invalid_reason": None}
        except (StopRun, ValueError, TypeError, KeyError, AttributeError):
            return {**base, "technical_status": "invalid", "vote": None, "invalid_reason": "transport_identity_completion_or_schema"}

    def vote(self, cell):
        try:
            result = self.paid_cell(cell)
            parsed = self._parsed(cell, result)
            immutable(self.scope / "votes" / (cell["call_id"] + ".json"), encode(parsed))
            if parsed["operational_failure"]:
                with self.locked():
                    self._record_operational_failure(cell["call_id"])
            return parsed
        except StopRun as exc:
            directory = self.calls / cell["call_id"]
            reserved, intended = (directory / "reservation.json").exists(), (self.scope / "intents" / (cell["call_id"] + ".json")).exists()
            return {"call_id": cell["call_id"], "item_id": cell["item_id"], "round_number": cell["round_number"],
                    "vote_index": cell["vote_index"], "audit": cell["audit"], "technical_status": "unresolved_attempt" if reserved else "unresolved_intent" if intended else "not_dispatched",
                    "request_state": "unknown" if reserved or intended else "not_dispatched", "vote": None, "stop_reason": str(exc)}

    def _item_cells(self, item_id, round_number, audit=False):
        return sorted((cell for cell in self.plan["cells"] if cell["item_id"] == item_id and cell["round_number"] == round_number
                       and cell["audit"] == audit), key=lambda cell: cell["vote_index"])

    def _condition_eligible(self, cell):
        if cell["round_number"] == 1 and not cell["audit"]:
            return
        first = []
        for original in self._item_cells(cell["item_id"], 1):
            cached = self._cached(original)
            require(cached is not None, "Conditional/audit vote cannot precede all original first-round observations")
            first.append(self._parsed(original, cached)["vote"])
        if cell["audit"]:
            require(cell["item_id"] in self.audit_ids and all(vote is not None for vote in first),
                    "Audit blocked by technically incomplete original panel; no unknown retry under another identity")
        else:
            require(annotation.panel_result(first, 1).get("next_round") == 2,
                    "Semantic second round requires a complete valid first panel without majority")

    def _process_item(self, item_id):
        first = [self.vote(cell) for cell in self._item_cells(item_id, 1)]
        first_votes = [row["vote"] for row in first]
        panel = annotation.panel_result(first_votes, 1)
        second = []
        if panel.get("next_round") == 2:
            second = [self.vote(cell) for cell in self._item_cells(item_id, 2)]
        primary = annotation.resolve_primary(first_votes, [row["vote"] for row in second] if second else None)
        return {"item_id": item_id, "round1": first, "round2": second, "primary": primary}

    def _needs_new(self):
        for item_id in self.item_lookup:
            first = []
            for cell in self._item_cells(item_id, 1):
                if not (self.calls / cell["call_id"]).exists() and not (self.scope / "intents" / (cell["call_id"] + ".json")).exists():
                    return True
                try:
                    with self.locked():
                        cached = self._cached(cell)
                    first.append(self._parsed(cell, cached)["vote"] if cached is not None else None)
                except StopRun:
                    first.append(None)
            eligible = self._item_cells(item_id, 2) if annotation.panel_result(first, 1).get("next_round") == 2 else []
            if item_id in self.audit_ids and all(vote is not None for vote in first):
                eligible += self._item_cells(item_id, 1, True)
            if any(not (self.calls / cell["call_id"]).exists() and not (self.scope / "intents" / (cell["call_id"] + ".json")).exists()
                   for cell in eligible):
                return True
        return False

    def run(self):
        require(self.execute_enabled, "Use --collect --execute for the finite machine-only run")
        self._check_sources()
        deadline = datetime.fromisoformat(self.settings.deadline.replace("Z", "+00:00"))
        if self._needs_new() and self.settings.key and datetime.now(timezone.utc) < deadline:
            self.preflight()
        items = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self._process_item, item_id): item_id for item_id in self.item_lookup}
            for future in as_completed(futures):
                items[futures[future]] = future.result()
        audits = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}
            for item_id in self.audit_ids:
                if all(row["vote"] is not None for row in items[item_id]["round1"]):
                    futures[pool.submit(lambda item_id=item_id: [self.vote(cell) for cell in self._item_cells(item_id, 1, True)])] = item_id
                else:
                    audits[item_id] = {"status": "not_dispatched_first_panel_technical_unresolved", "votes": []}
            for future in as_completed(futures):
                audits[futures[future]] = {"status": "completed_audit_attempts", "votes": future.result()}
        executed = {row["call_id"]: row for item in items.values() for key in ("round1", "round2") for row in item[key]}
        executed.update({row["call_id"]: row for audit in audits.values() for row in audit["votes"]})
        registry = []
        for cell in self.plan["cells"]:
            registry.append(executed.get(cell["call_id"], {**cell, "technical_status": "not_scheduled_by_fixed_condition",
                            "request_state": "not_dispatched", "vote": None}))
        with self.locked():
            ledger = self._read_retained_ledger()
            output = {"schema_version": 1, "phase": "machine_development_annotation",
                      "protocol_sha256": self.protocol_digest, "items_sha256": self.items_digest,
                      "source_inventory_sha256": self.source_inventory_digest, "dispatch_plan_sha256": sha(encode(self.plan)),
                      "items": [items[item_id] for item_id in sorted(items)], "audits": audits, "all_planned_calls": registry,
                      "maximum_calls": len(registry), "charged_or_reserved_rub": str(ledger.committed), "completed_utc": utcnow(),
                      "E0": "not_passed", "human_gold": "not_created", "scientific_validity": "not_assessed",
                      "audit_effect_on_primary_consensus": "none"}
            self.save(self.scope / "results.json", output)
        return output


class MachineDevelopmentRunner(CooperativeLedgerIOMixin, _MachineCore):
    """Explicitly source-bound new execution adapter; old collectors unchanged."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--dry-run", action="store_true")
    commands.add_argument("--preflight", action="store_true")
    commands.add_argument("--collect", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=PROJECT / ".research/resumption-2026-11-08-live")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.execute != args.collect:
        parser.error("--collect and --execute must be supplied together")
    try:
        values = {**(parse_env(args.env_file) if args.env_file else {}), **os.environ}
        require(values.get("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1") == "https://routerai.ru/api/v1", "Only RouterAI is authorized")
        runner = MachineDevelopmentRunner(MachineSettings(state=args.state, key=values.get("ROUTERAI_API_KEY", ""),
            cap=Decimal(3300), collection_cap=Decimal(3300), top_p=1.0, max_tokens=1024), args.protocol, execute=args.execute)
        if args.dry_run:
            result = {"dry_run": True, "paid_requests": 0, "items": len(runner.items), "maximum_calls": len(runner.plan["cells"]),
                      "scope": str(runner.scope), "protocol_sha256": runner.protocol_digest, "source_inventory_sha256": runner.source_inventory_digest}
        elif args.preflight:
            result = {key: value for key, value in runner.preflight().items() if key != "cells"}
        else:
            result = {key: value for key, value in runner.run().items() if key not in ("items", "audits", "all_planned_calls")}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except StopRun as exc:
        print(json.dumps({"stopped": True, "reason": str(exc), "E0": "not_passed"}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
