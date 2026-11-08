"""Finite Stage-A collection with a new binding and the existing shared budget.

The v1 protocol, source closure, admissions and proofs remain unchanged. New
generation requests use pilot-v2 identities and the same global ledger, OS lock
and calls directory. No embedding or prediction-fitting path is provided.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import zipfile

from resumption.runner import Runner, Settings, sha, read_json, utcnow, HISTORICAL_ARCHIVE, HISTORICAL_MEMBER, HISTORICAL_SHA
from stage0.config import parse_env
from stage0.runner import StopRun, Ledger, encode, estimate, redact
from stage0.traces import inspect_trace


PROJECT = Path(__file__).resolve().parents[1]
PROVIDERS = {"deepseek/deepseek-v4.1-flash": "BytePlus", "openai/gpt-oss-20b": "DeepInfra"}
FINAL_STATUS = "prospective_frozen_development_probe"
KIND = "pilot_v2_generation"


def require(condition, message):
    if not condition:
        raise StopRun(message)


def immutable(path, data):
    if path.exists():
        require(path.read_bytes() == data, "Pilot-v2 immutable artifact changed")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def corpus_tasks(document):
    tasks = document.get("tasks")
    require(isinstance(tasks, list) and len(tasks) == 48, "Stage A requires exactly 48 frozen tasks")
    roots = defaultdict(list)
    seen = set()
    for task in tasks:
        require(isinstance(task.get("task_id"), str) and task["task_id"] not in seen
                and isinstance(task.get("root_id"), str) and isinstance(task.get("prompt"), str)
                and bool(task["prompt"]), "Invalid or duplicate pilot-v2 task identity/prompt")
        require(task.get("split") == "development" and task.get("confirmatory_excluded") is True,
                "Stage-A tasks must remain development-only")
        seen.add(task["task_id"])
        roots[task["root_id"]].append(task)
    require(len(roots) == 24 and all(len(members) == 2 for members in roots.values()),
            "Stage A requires 24 paired roots")
    strata = defaultdict(list)
    for root, members in roots.items():
        attributes = {(task["domain"], task.get("tier", task.get("difficulty"))) for task in members}
        require(len(attributes) == 1, "One root crosses construction strata")
        strata[next(iter(attributes))].append((root, sorted(members, key=lambda task: task["task_id"])))
    require(len(strata) == 12 and all(len(values) == 2 for values in strata.values()),
            "Stage A requires four domains by three tiers by two roots")
    queues = {key: deque(sorted(values, key=lambda value: sha(encode(["pilot-v2-allocation", value[0]]))))
              for key, values in strata.items()}
    ordered = []
    while any(queues.values()):
        for key in sorted(queues):
            if queues[key]:
                ordered.append(queues[key].popleft())
    return tasks, ordered


class PilotV2Runner(Runner):
    def __init__(self, settings, protocol_path, corpus_path, transport=None, *, project=PROJECT, execute=False,
                 fixture_verifier=None):
        self.project = Path(project).resolve(strict=True)
        self.protocol_path, self.corpus_path = Path(protocol_path), Path(corpus_path)
        protocol_bytes, corpus_bytes = self.protocol_path.read_bytes(), self.corpus_path.read_bytes()
        self.protocol, self.corpus = json.loads(protocol_bytes), json.loads(corpus_bytes)
        p, g, b = self.protocol, self.protocol["generation"], self.protocol["budget"]
        require(p.get("schema_version") == 1 and p.get("status") == FINAL_STATUS,
                "Pilot-v2 protocol is not finalized for this finite development probe")
        require(g.get("output_budget_tokens") == [2048, 8192] and g.get("samples_per_task") == 1
                and g.get("max_calls") == 192 and g.get("temperature") == .7 and g.get("top_p") == .95
                and g.get("seed") == 42 and g.get("concurrency_max") == 3
                and g.get("request_timeout_seconds") == 180 and g.get("automatic_retries") == 0
                and g.get("operational_failure_limit_per_route") == 2, "Unapproved pilot-v2 generation parameters")
        require(p.get("measurement", {}).get("allow_budget_censored_gradeable") is False
                and p["measurement"].get("embeddings_in_stage_A") is False,
                "Stage A requires stop-only primary eligibility and no embeddings")
        require(p["tasks"].get("file_sha256") == sha(corpus_bytes)
                and p["tasks"].get("tasks") == 48 and p["tasks"].get("roots") == 24,
                "Pilot-v2 corpus differs from its prospective protocol")
        models = p.get("models")
        require(isinstance(models, list) and len(models) == 2
                and {row.get("model"): row.get("provider") for row in models} == PROVIDERS,
                "Only the two declared inherited model/provider routes are allowed")
        self.model_specs = {row["model"]: row for row in models}
        self.launch_amount = Decimal(p["parent"]["launch_charged_or_reserved_rub"])
        self.stage_ceiling = Decimal(b["absolute_stage_ceiling_rub"])
        require(Decimal(b["cap_total_rub"]) == Decimal(3000) == settings.cap
                and Decimal(b["stage_additional_cap_rub"]) == Decimal(1200)
                and self.stage_ceiling == self.launch_amount + Decimal(1200) <= settings.cap,
                "Pilot-v2 shared or additional budget differs from authorization")
        expected_state = (self.project / b["shared_state"]).resolve(strict=True)
        require(settings.state.resolve(strict=True) == expected_state
                and all((expected_state / name).is_file() for name in
                        ("ledger.json", "protocol.json", "corpus.json", "source-inventory.json", "dispatch-window.json")),
                "Pilot v2 must use the existing shared state and ledger")
        original_window = read_json(expected_state / "dispatch-window.json")["deadline"]
        deadline = datetime.fromisoformat(g["dispatch_deadline_utc"].replace("Z", "+00:00"))
        old_deadline = datetime.fromisoformat(original_window.replace("Z", "+00:00"))
        require(deadline.tzinfo is not None and deadline <= old_deadline,
                "Pilot v2 cannot extend the original paid dispatch deadline")
        settings.deadline, settings.timeout, settings.concurrency = g["dispatch_deadline_utc"], 180, 3
        require(settings.temperature == .7 and settings.top_p == .95 and settings.seed == 42,
                "Runtime sampling differs from the prospective protocol")
        self.scope = expected_state / "pilot-v2" / sha(protocol_bytes)
        self.execute_enabled = execute
        self.preflight_ready = False
        self.active_cost_plan_sha256 = None
        require(fixture_verifier is None or transport is not None and p.get("synthetic_fixture") is True,
                "A live run cannot replace the independent task verifier")
        self.fixture_verifier = fixture_verifier
        super().__init__(settings, transport)
        self.protocol_digest, self.tasks_digest = sha(protocol_bytes), sha(corpus_bytes)
        self.tasks, ordered = corpus_tasks(self.corpus)
        self.task_lookup = {task["task_id"]: task for task in self.tasks}
        self._verify_parent()
        with self.locked():
            self.scope.mkdir(parents=True, exist_ok=True)
            immutable(self.scope / "protocol.json", protocol_bytes)
            immutable(self.scope / "corpus.json", corpus_bytes)
            launch_path = self.scope / "ledger-launch.json"
            if not launch_path.exists():
                current = self.ledger_path.read_bytes()
                require(sha(current) == p["parent"]["launch_ledger_sha256"],
                        "Shared ledger changed before the pilot-v2 launch snapshot")
                immutable(launch_path, current)
            self.launch_rows = read_json(launch_path)
            require(len(self.launch_rows) == p["parent"]["launch_ledger_rows"]
                    and sha(launch_path.read_bytes()) == p["parent"]["launch_ledger_sha256"]
                    and sum((Decimal(row["charged_or_reserved_rub"]) for row in self.launch_rows), Decimal(0)) == self.launch_amount,
                    "Pilot-v2 launch commitments do not match the frozen parent ledger")
            self._freeze_v2_sources()
            self.plan = self._make_plan(ordered)
            immutable(self.scope / "dispatch-plan.json", encode(self.plan))
            self._read_retained_ledger()

    def _initialize_ledger(self):
        # Unlike dispatch admission, read-only recovery/finalization must remain
        # possible after a reported overrun. Never initialize or reset a ledger.
        require(self.ledger_path.is_file(), "Pilot v2 cannot create a separate budget ledger")
        with zipfile.ZipFile(HISTORICAL_ARCHIVE) as archive:
            original = archive.read(HISTORICAL_MEMBER)
        require(sha(original) == HISTORICAL_SHA, "Historical ledger source changed")
        self.historical_rows = json.loads(original)
        with self.locked():
            self._read_retained_ledger()

    def _read_retained_ledger(self):
        ledger = Ledger(self.ledger_path, self.settings.cap)
        require(ledger.rows[:len(self.historical_rows)] == self.historical_rows,
                "Historical ledger rows changed or disappeared")
        if hasattr(self, "launch_rows"):
            require(ledger.rows[:len(self.launch_rows)] == self.launch_rows, "Prior pilot commitments changed or disappeared")
        for row in ledger.rows:
            value = Decimal(row["charged_or_reserved_rub"])
            require(value.is_finite() and value >= 0, "Invalid retained budget commitment")
        return ledger

    def _verify_parent(self):
        parent = self.protocol["parent"]
        require(sha((self.state / "protocol.json").read_bytes()) == parent["protocol_sha256"]
                and sha((self.state / "source-inventory.json").read_bytes()) == parent["source_inventory_sha256"],
                "The inherited v1 protocol or source proof changed")
        for relative, digest in read_json(self.state / "source-inventory.json")["files"].items():
            require(sha((self.project / relative).read_bytes()) == digest,
                    "The inherited v1 source code changed")
        with self.locked():
            ledger_ids = {row["id"] for row in self._read_retained_ledger().rows}
        for model, spec in self.model_specs.items():
            directory = self.calls / spec["parent_admission_call_id"]
            request_bytes, response_bytes = (directory / "request.json").read_bytes(), (directory / "response.json").read_bytes()
            request, response = json.loads(request_bytes), json.loads(response_bytes)
            reservation, result = read_json(directory / "reservation.json"), read_json(directory / "result.json")
            require(reservation.get("request_sha256") == sha(request_bytes)
                    and result.get("response_sha256") == sha(response_bytes)
                    and result.get("response") == response
                    and result.get("reservation_id") == reservation.get("reservation_id")
                    and result.get("protocol_sha256") == parent["protocol_sha256"]
                    and reservation.get("reservation_id") in ledger_ids,
                    "Inherited admission is not linked to the retained shared ledger/raw result")
            payload = response.get("json", {})
            require(sha(request_bytes) == spec["parent_request_sha256"]
                    and sha(response_bytes) == spec["parent_response_sha256"]
                    and request.get("model") == payload.get("model") == model
                    and payload.get("provider") == spec["provider"] and response.get("http_status") == 200
                    and payload.get("error") is None and request.get("reasoning", {}).get("enabled") is True
                    and request.get("include_reasoning") is True
                    and inspect_trace(payload)["status"] == "visible_trace_candidate",
                    "Inherited model/provider admission is absent or changed")

    def _sources(self):
        paths = sorted((self.project / "pilot_v2").glob("*.py"))
        old = read_json(self.state / "source-inventory.json")["files"]
        paths += [self.project / relative for relative in old]
        return {path.relative_to(self.project).as_posix(): path.read_bytes() for path in sorted(set(paths))}

    def _freeze_v2_sources(self):
        sources = self._sources()
        require("pilot_v2/runner.py" in sources and "pilot_v2/tasks.py" in sources,
                "Pilot-v2 runner and independent verifier sources are required")
        inventory = {"schema_version": 1, "scope": "all pilot_v2/*.py plus exact inherited collector closure",
                     "files": {name: sha(data) for name, data in sorted(sources.items())}}
        for name, data in sources.items():
            require(not self.settings.key or self.settings.key.encode() not in data, "Credential literal found in source")
            immutable(self.scope / "source" / name, data)
        immutable(self.scope / "source-inventory.json", encode(inventory))
        self.source_inventory_digest = sha(encode(inventory))
        self.verifier_source_digest = inventory["files"]["pilot_v2/tasks.py"]

    def _check_sources(self):
        inventory = read_json(self.scope / "source-inventory.json")
        require(sha((self.scope / "source-inventory.json").read_bytes()) == self.source_inventory_digest
                and {name: sha(data) for name, data in self._sources().items()} == inventory["files"],
                "Pilot-v2 code changed after source freeze")
        require(sha(self.protocol_path.read_bytes()) == self.protocol_digest
                and sha(self.corpus_path.read_bytes()) == self.tasks_digest,
                "Pilot-v2 protocol/corpus changed after binding")
        for name, digest in inventory["files"].items():
            require(sha((self.scope / "source" / name).read_bytes()) == digest, "Frozen pilot-v2 source snapshot changed")
        self._verify_parent()

    def _check_shared_budget(self):
        ledger = self._check_ledger()
        require(ledger.rows[:len(self.launch_rows)] == self.launch_rows,
                "Prior pilot commitments changed or disappeared")
        require(ledger.committed <= self.stage_ceiling, "Pilot-v2 additional stage budget is exhausted")
        return ledger

    def _make_plan(self, ordered):
        cells = []
        models = sorted(self.model_specs)
        caps = self.protocol["generation"]["output_budget_tokens"]
        for root_index, (root, members) in enumerate(ordered):
            # Rotate factor order per root, without looking at any response.
            conditions = [(model, cap) for model in models for cap in caps]
            shift = root_index % len(conditions)
            conditions = conditions[shift:] + conditions[:shift]
            if root_index % 2:
                members = list(reversed(members))
            for model, cap in conditions:
                for task in members:
                    identity = {"protocol_sha256": self.protocol_digest, "root_id": root, "task_id": task["task_id"],
                                "model": model, "provider": self.model_specs[model]["provider"],
                                "output_budget_tokens": cap, "sample_index": 0}
                    condition = sha(encode(identity))
                    seed = 42 + int(sha(encode([root, task["task_id"], model, 0]))[:7], 16)
                    cell = {**identity, "condition_id": condition, "seed": seed,
                            "domain": task["domain"], "tier": task.get("tier", task.get("difficulty"))}
                    cell["call_id"] = sha(encode({"kind": KIND, "identity": [condition, 0],
                                                  "protocol": self.protocol_digest, "model": model}))
                    cell["request_sha256"] = sha(encode(self.body(cell)))
                    cells.append(cell)
        require(len(cells) == 192 and len({cell["call_id"] for cell in cells}) == 192,
                "Prospective Stage-A call roster differs from 192 unique cells")
        return {"schema_version": 1, "protocol_sha256": self.protocol_digest, "corpus_sha256": self.tasks_digest,
                "source_inventory_sha256": self.source_inventory_digest, "schedule": "root_stratified_rotating_factor_blocks_v1",
                "cells": cells}

    def body(self, cell):
        return {"model": cell["model"], "messages": [{"role": "user", "content": self.task_lookup[cell["task_id"]]["prompt"]}],
                "max_tokens": cell["output_budget_tokens"], "temperature": .7, "top_p": .95, "seed": cell["seed"],
                "stream": False, "reasoning": {"enabled": True}, "include_reasoning": True,
                "provider": {"order": [cell["provider"]], "allow_fallbacks": False}}

    def _metadata(self, path, name):
        response = self.transport(path, timeout=30)
        record = {"retrieved_at": utcnow(), "endpoint": path,
                  "response": {key: value for key, value in response.items() if key != "headers"}}
        receipt = self.save(self.scope / "metadata" / (name + ".json"), record)
        self.save(self.scope / "metadata/history" / (receipt + ".json"), record)
        require(response.get("http_status") == 200 and not response.get("json", {}).get("error"),
                "Pilot-v2 quotation metadata is unavailable")
        return {**response, "metadata_receipt_sha256": receipt}

    def preflight(self, refresh=True):
        self._check_sources()
        path = self.scope / "cost-plan.json"
        if path.exists() and not refresh:
            plan = read_json(path)
            require(plan["dispatch_plan_sha256"] == sha(encode(self.plan)), "Cost plan uses another prospective roster")
            return plan
        self.prices.clear()
        self.price_receipts.clear()
        rows = []
        for cell in self.plan["cells"]:
            price = self.price(cell["model"], cell["provider"])
            attempted = ((self.calls / cell["call_id"]).exists() or
                         (self.scope / "intents" / (cell["call_id"] + ".json")).exists())
            rows.append({"call_id": cell["call_id"], "reservation_rub": str(estimate(self.body(cell), price)),
                         "previously_attempted": attempted,
                         "prompt_rub_per_token": str(price[0]), "completion_rub_per_token": str(price[1]),
                         "quote_receipt_sha256": self.price_receipts[(cell["model"], cell["provider"])]})
        total = sum((Decimal(row["reservation_rub"]) for row in rows), Decimal(0))
        remaining = sum((Decimal(row["reservation_rub"]) for row in rows if not row["previously_attempted"]), Decimal(0))
        with self.locked():
            ledger = self._check_shared_budget()
            plan = {"schema_version": 1, "created_utc": utcnow(), "paid_requests": 0,
                    "dispatch_plan_sha256": sha(encode(self.plan)), "protocol_sha256": self.protocol_digest,
                    "source_inventory_sha256": self.source_inventory_digest, "cells": rows,
                    "full_roster_reservation_rub": str(total), "launch_charged_or_reserved_rub": str(self.launch_amount),
                    "remaining_new_reservation_rub": str(remaining),
                    "absolute_stage_ceiling_rub": str(self.stage_ceiling),
                    "full_roster_fits_stage_budget": ledger.committed + remaining <= self.stage_ceiling,
                    "current_shared_charged_or_reserved_rub": str(ledger.committed)}
            digest = sha(encode(plan))
            immutable(self.scope / "cost-plans" / (digest + ".json"), encode(plan))
            self.save(path, plan)
        self.preflight_ready = True
        self.active_cost_plan_sha256 = digest
        return plan

    def _route_state(self):
        path = self.scope / "route-state.json"
        return read_json(path) if path.exists() else {"schema_version": 1, "operational_failure_calls": {}}

    def _cached(self, cell, body):
        directory = self.calls / cell["call_id"]
        if not directory.exists():
            require(not (self.scope / "intents" / (cell["call_id"] + ".json")).exists(),
                    "Unfinalized pilot-v2 intent cannot be retried")
            return None
        result = self._cached_call(directory, encode(body))
        response_path, request_path = directory / "response.json", directory / "request.json"
        require(response_path.is_file() and sha(response_path.read_bytes()) == result["response_sha256"]
                and json.loads(response_path.read_bytes()) == result["response"]
                and sha(request_path.read_bytes()) == result["request_sha256"]
                and result["protocol_sha256"] == self.protocol_digest and result["corpus_sha256"] == self.tasks_digest
                and result["source_inventory_sha256"] == self.source_inventory_digest,
                "Cached pilot-v2 observation differs from its binding")
        ledger = self._read_retained_ledger()
        require(any(row["id"] == result["reservation_id"] for row in ledger.rows),
                "Cached observation is missing its shared budget reservation")
        return result

    def paid_cell(self, cell):
        require(self.execute_enabled, "Paid pilot-v2 execution requires explicit --execute")
        self._check_sources()
        require(cell in self.plan["cells"], "Requested cell is outside the frozen prospective roster")
        body = self.body(cell)
        require(sha(encode(body)) == cell["request_sha256"], "Pilot-v2 request parameters changed")
        with self.locked():
            cached = self._cached(cell, body)
            if cached is not None:
                return cached
            self._check_shared_budget()
        require(self.preflight_ready and self.active_cost_plan_sha256 is not None,
                "Run a fresh full remaining-roster preflight in this process before paid dispatch")
        require(read_json(self.scope / "cost-plan.json")["full_roster_fits_stage_budget"] is True,
                "The complete prospective Stage-A reservation does not fit its stage budget")
        require(bool(self.settings.key), "ROUTERAI_API_KEY is not configured")
        self._deadline()
        price = self.price(cell["model"], cell["provider"])
        amount = estimate(body, price)
        with self.locked():
            cached = self._cached(cell, body)
            if cached is not None:
                return cached
            self._deadline()
            route_state = self._route_state()
            route_key = cell["model"] + "|" + cell["provider"]
            require(len(route_state["operational_failure_calls"].get(route_key, [])) < 2,
                    "Pilot-v2 route stopped after two observed operational failures")
            ledger = self._check_shared_budget()
            require(ledger.committed + amount <= self.stage_ceiling and ledger.committed + amount <= self.settings.cap,
                    "Pilot-v2 reservation would exceed the shared/stage ceiling")
            intent = {"schema_version": 1, "cell": cell, "request_sha256": cell["request_sha256"],
                      "protocol_sha256": self.protocol_digest, "source_inventory_sha256": self.source_inventory_digest}
            immutable(self.scope / "intents" / (cell["call_id"] + ".json"), encode(intent))
            directory = self.calls / cell["call_id"]
            directory.mkdir()
            request_digest = self.save(directory / "request.json", body)
            row = ledger.reserve(amount, "pilot_v2:generation:" + cell["model"])
            context = {"call_id": cell["call_id"], "kind": KIND, "identity": [cell["condition_id"], 0],
                "model": cell["model"], "provider": cell["provider"], "condition_id": cell["condition_id"],
                "task_id": cell["task_id"], "root_id": cell["root_id"], "sample_index": 0,
                "output_budget_tokens": cell["output_budget_tokens"], "protocol_sha256": self.protocol_digest,
                "corpus_sha256": self.tasks_digest, "source_inventory_sha256": self.source_inventory_digest,
                "verifier_source_sha256": self.verifier_source_digest, "parent_protocol_sha256": self.protocol["parent"]["protocol_sha256"],
                "request_sha256": request_digest, "reservation_id": row["id"], "reservation_rub": str(amount),
                "quote_receipt_sha256": self.price_receipts[(cell["model"], cell["provider"])],
                "quote_namespace": self.scope.relative_to(self.state).as_posix() + "/metadata/history",
                "cost_plan_sha256": self.active_cost_plan_sha256,
                "quoted_prompt_rub_per_token": str(price[0]), "quoted_completion_rub_per_token": str(price[1]),
                "reserved_at": utcnow(), "automatic_retries": 0}
            self.save(directory / "reservation.json", context)
        try:
            response = self.transport("/chat/completions", key=self.settings.key, body=body, timeout=180)
        except Exception as exc:
            response = {"http_status": None, "json": {}, "network_error": type(exc).__name__}
        safe = {key: value for key, value in response.items() if key != "headers"}
        response_digest = self.save(directory / "response.json", safe)
        with self.locked():
            ledger = self._read_retained_ledger()
            row = next(row for row in ledger.rows if row["id"] == context["reservation_id"])
            try:
                ledger.finish(row, safe)
            except StopRun:
                pass  # Actual overrun is persisted and blocks every subsequent call.
            result = {**context, "response": safe, "response_sha256": response_digest,
                      "http_status": safe.get("http_status"), "ledger_sha256": sha(self.ledger_path.read_bytes()),
                      "budget_overrun": ledger.committed > self.stage_ceiling or ledger.committed > self.settings.cap,
                      "completed_at": utcnow()}
            self.save(directory / "result.json", result)
        return result

    def execute_cell(self, cell):
        result = self.paid_cell(cell)
        payload = result["response"].get("json", {})
        try:
            inspected = inspect_trace(payload)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError):
            inspected = {"status": "unavailable", "trace": "", "answer": "", "finish_reason": None, "source": None}
        choices = payload.get("choices") or []
        message = choices[0].get("message", {}) if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = message if isinstance(message, dict) else {}
        details = message.get("reasoning_details") or []
        details = details if isinstance(details, list) else []
        encrypted = any(isinstance(item, dict) and item.get("type") == "reasoning.encrypted" for item in details)
        summary = inspected.get("summary_present", False)
        identity_ok = payload.get("model") == cell["model"] and payload.get("provider") == cell["provider"]
        api_ok = result["http_status"] == 200 and payload.get("error") is None
        visible = bool(inspected["trace"].strip()) and not summary and not encrypted
        operational_failure = not (api_ok and identity_ok and visible)
        censored = not operational_failure and inspected["finish_reason"] == "length"
        completed = not operational_failure and inspected["status"] == "visible_trace_candidate" and inspected["finish_reason"] == "stop"
        text = inspected["trace"].split("ANSWER:", 1)[0]
        verifier = self.fixture_verifier
        if verifier is None:
            from pilot_v2.tasks import verify_answer
            verifier = verify_answer
        try:
            raw_grading = verifier(self.task_lookup[cell["task_id"]], inspected["answer"])
        except (ValueError, TypeError, KeyError):
            raw_grading = {"verdict": "unparseable", "correct": None, "gradable": False, "verifier_error": True}
        correct = {"correct": True, "incorrect": False}.get(raw_grading.get("verdict")) if completed else None
        record = {**{key: cell[key] for key in ("task_id", "root_id", "model", "provider", "output_budget_tokens", "sample_index", "condition_id", "seed", "domain", "tier")},
            "trace_id": cell["call_id"], "difficulty": cell["tier"], "split": "development", "confirmatory_excluded": True,
            "status": "completed" if completed else "truncated" if censored else "excluded",
            "observed_generation_status": "completed" if completed else "budget_censored" if censored else "excluded",
            "budget_censored": censored, "finish_reason": inspected["finish_reason"],
            "observed_trace_status": inspected["status"], "text": text, "raw_reasoning_text": inspected["trace"],
            "raw_reasoning_sha256": sha(inspected["trace"].encode("utf-8")), "reasoning_source": inspected.get("source"),
            "answer": inspected["answer"], "correct": correct, "gradable": type(correct) is bool,
            "raw_answer_grading": raw_grading, "operational_failure": operational_failure,
            "http_status": result["http_status"],
            "request_state": "unknown" if result["http_status"] is None or result["response"].get("network_error") else "finished",
            "identity_verified": identity_ok, "provider_route_verified": payload.get("provider") == cell["provider"],
            "full_visible_trace": False, "E0": "not_passed", "phase": "pilot_v2_stage_A",
            "protocol_sha256": self.protocol_digest, "corpus_sha256": self.tasks_digest,
            "source_inventory_sha256": self.source_inventory_digest, "verifier_source_sha256": self.verifier_source_digest,
            "request_sha256": result["request_sha256"], "response_sha256": result["response_sha256"],
            "reservation_id": result["reservation_id"], "attempted": True,
            "reused_record_without_resend": bool(result.get("reused_record_without_resend"))}
        with self.locked():
            trace_path = self.calls / cell["call_id"] / "trace.json"
            if trace_path.exists():
                previous = read_json(trace_path)
                require({key: value for key, value in previous.items() if key != "reused_record_without_resend"} ==
                        {key: value for key, value in record.items() if key != "reused_record_without_resend"},
                        "Cached pilot-v2 trace differs from its first recorded observation")
            else:
                self.save(trace_path, record)
            if operational_failure:
                state = self._route_state()
                key = cell["model"] + "|" + cell["provider"]
                failures = state["operational_failure_calls"].setdefault(key, [])
                if cell["call_id"] not in failures:
                    failures.append(cell["call_id"])
                    self.save(self.scope / "route-state.json", state)
        return record

    def run(self):
        require(self.execute_enabled, "Use --run --execute for authorized paid execution")
        need_new = any(not (self.calls / cell["call_id"]).exists()
                       and not (self.scope / "intents" / (cell["call_id"] + ".json")).exists()
                       for cell in self.plan["cells"])
        # Refresh quotations for the complete remaining fixed allocation in this
        # process, so paid_cell uses the very same pinned-provider quote cache.
        # After cutoff/no credential, cached observations still recover offline.
        deadline = datetime.fromisoformat(self.settings.deadline.replace("Z", "+00:00"))
        with self.locked():
            current = self._read_retained_ledger().committed
        if need_new and current < min(self.stage_ceiling, self.settings.cap) and self.settings.key and datetime.now(timezone.utc) < deadline:
            self.preflight(refresh=True)
        records = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self.execute_cell, cell): cell for cell in self.plan["cells"]}
            for future in as_completed(futures):
                cell = futures[future]
                try:
                    records[cell["call_id"]] = future.result()
                except StopRun as exc:
                    reserved = (self.calls / cell["call_id"] / "reservation.json").exists()
                    intended = (self.scope / "intents" / (cell["call_id"] + ".json")).exists()
                    attempted = True if reserved else None if intended else False
                    records[cell["call_id"]] = {**cell, "trace_id": cell["call_id"], "split": "development",
                        "phase": "pilot_v2_stage_A",
                        "status": "unresolved_attempt" if reserved else "unresolved_intent" if intended else "not_dispatched",
                        "request_state": "unknown" if reserved or intended else "not_dispatched", "http_status": None,
                        "attempted": attempted, "correct": None, "gradable": False, "text": "", "stop_reason": str(exc)}
        with self.locked():
            ledger = self._read_retained_ledger()
            output = {"schema_version": 1, "phase": "pilot_v2_stage_A", "protocol_sha256": self.protocol_digest,
                "corpus_sha256": self.tasks_digest, "source_inventory_sha256": self.source_inventory_digest,
                "dispatch_plan_sha256": sha(encode(self.plan)), "records": [records[cell["call_id"]] for cell in self.plan["cells"]],
                "all_planned_cells": 192, "charged_or_reserved_rub": str(ledger.committed),
                "E0": "not_passed", "scientific_validity": "not_assessed", "completed_utc": utcnow()}
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
    if args.execute and not args.run:
        parser.error("--execute is only accepted together with --run")
    if args.run and not args.execute:
        parser.error("--run requires the explicit --execute flag")
    try:
        values = {**(parse_env(args.env_file) if args.env_file else {}), **os.environ}
        require(values.get("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1") == "https://routerai.ru/api/v1",
                "Only the prescribed RouterAI URL is allowed")
        settings = Settings(state=args.state, key=values.get("ROUTERAI_API_KEY", ""), cap=Decimal(3000), collection_cap=Decimal(3000))
        runner = PilotV2Runner(settings, args.protocol, args.tasks, execute=args.execute)
        if args.dry_run:
            result = {"dry_run": True, "paid_requests": 0, "planned_cells": 192,
                      "scope": runner.scope.relative_to(PROJECT).as_posix(), "protocol_sha256": runner.protocol_digest,
                      "source_inventory_sha256": runner.source_inventory_digest}
        elif args.preflight:
            result = runner.preflight()
            result = {key: value for key, value in result.items() if key != "cells"}
        else:
            output = runner.run()
            result = {key: value for key, value in output.items() if key != "records"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except StopRun as exc:
        print(json.dumps({"stopped": True, "reason": str(exc)}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
