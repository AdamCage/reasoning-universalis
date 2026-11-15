"""Finite, approval-gated new condition in the existing shared budget journal."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path

from cross_model.annotation import probe_item, request_body, validate_envelope
from cross_model.common import ARTIFACT, PROTOCOL, ROUTES, immutable, read, sha, utcnow, write
from resumption.runner import Runner as ParentRunner, ceiling_rates
from stage0.config import parse_env
from stage0.runner import Ledger, estimate, http


def cells(document, codebook):
    roster = []
    for model, provider in ROUTES:
        for condition, items in (("schema_probe", [probe_item()]), ("full_context", document["items"]),
                                 ("without_context", [i for i in document["items"] if i["item_id"] in document["ablation_ids"]])):
            for item in items:
                roster.append({"model": model, "provider": provider, "condition": condition, "item_id": item["item_id"],
                               "request": request_body(item, codebook, model, provider, condition)})
    return roster


def quote(project):
    project = Path(project)
    base = project / ARTIFACT
    document, codebook = read(base / "input-items.json"), read(base / "codebook.json")
    roster, costs, details = cells(document, codebook), [], []
    for model, provider in ROUTES:
        receipt_path = base / "metadata" / (model.replace("/", "_") + ".json")
        receipt = read(receipt_path)
        if receipt["response"].get("http_status") != 200 or receipt["paid_requests"] != 0:
            raise ValueError("No successful metadata-only receipt")
        routes = [e for e in receipt["response"]["json"]["data"]["endpoints"] if e["provider_name"] == provider]
        required = {"structured_outputs", "response_format", "seed", "max_tokens", "temperature", "top_p", "reasoning", "include_reasoning"}
        if not routes or any(e.get("status") != 0 or not required <= set(e.get("supported_parameters", [])) for e in routes):
            raise ValueError("Pinned route does not declare all frozen parameters")
        price = ceiling_rates(receipt["response"], provider)
        selected = [c for c in roster if c["model"] == model]
        from stage0.runner import encode
        bounds = [len(encode(c["request"])) + 2048 + c["request"]["max_tokens"] for c in selected]
        if max(bounds) > min(e["context_length"] for e in routes):
            raise ValueError("Conservative context bound exceeds route limit")
        total = sum((estimate(c["request"], price) for c in selected), Decimal(0))
        costs.append(total)
        details.append({"model": model, "provider": provider, "calls": len(selected), "prompt_rub_per_token_ceiling": str(price[0]),
            "completion_rub_per_token_ceiling": str(price[1]), "reservation_rub": str(total),
            "max_context_token_upper_bound": max(bounds), "metadata_path": receipt_path.relative_to(project).as_posix(),
            "metadata_sha256": sha(receipt_path.read_bytes()), "retrieved_utc": receipt["retrieved_utc"],
            "availability": "catalog_active; paid structured-output probe still required"})
    ledger_path = project / ".research/resumption-2026-11-08-live/ledger.json"
    launch = read(ledger_path)
    commitment = sum((Decimal(r["charged_or_reserved_rub"]) for r in launch), Decimal(0))
    if len(launch) != 2109 or commitment != Decimal("2038.3174633704220"):
        raise ValueError("Closed ledger differs; do not reset or discard obligations")
    total = sum(costs, Decimal(0))
    if total > 400 or commitment + total > 3300:
        raise ValueError("Complete roster does not fit proposed new budget")
    result = {"created_utc": utcnow(), "paid_requests": 0, "maximum_new_calls": len(roster), "routes": details,
        "worst_case_reservation_rub": str(total), "proposed_new_cap_rub": "400", "launch_rows": len(launch),
        "launch_charged_or_reserved_rub": str(commitment), "launch_ledger_sha256": sha(ledger_path.read_bytes()),
        "cumulative_with_full_roster_rub": str(commitment + total), "authorization": "pending_separate_user_confirmation",
        "estimate_rule": "2 * (UTF8(request)+2048 input tokens at max pinned-provider rate +4096 output tokens); min0.01/call; cache discounts ignored"}
    immutable(base / "ledger-launch.json", launch)
    # Time-stamped quote is written once; freezing protocol binds these bytes.
    target = base / "cost-quote.json"
    if target.exists():
        existing = read(target)
        if {k:v for k,v in existing.items() if k!='created_utc'} != {k:v for k,v in result.items() if k!='created_utc'}:
            raise ValueError("Existing quote differs")
        return existing
    write(target, result)
    return result


class Collector:
    locked = ParentRunner.locked

    def __init__(self, project, transport=http):
        self.project = Path(project).resolve()
        self.base = self.project / ARTIFACT
        self.protocol_path = self.project / PROTOCOL
        self.protocol = read(self.protocol_path)
        self.digest = sha(self.protocol_path.read_bytes())
        self.document, self.codebook = read(self.base / "input-items.json"), read(self.base / "codebook.json")
        self.items = {i["item_id"]: i for i in self.document["items"]}
        self.items[probe_item()["item_id"]] = probe_item()
        self.state = self.project / ".research/resumption-2026-11-08-live"
        self.ledger_path = self.state / "ledger.json"
        self.launch = read(self.base / "ledger-launch.json")
        self.launch_amount = sum((Decimal(r["charged_or_reserved_rub"]) for r in self.launch), Decimal(0))
        self.cap = min(Decimal(3300), self.launch_amount + Decimal(400))
        self.scope = self.state / "cross-model" / self.digest
        self.transport = transport
        self.quote = read(self.base / "cost-quote.json")
        self.roster = cells(self.document, self.codebook)
        self.verify_frozen()

    def verify_frozen(self):
        for path, digest in self.protocol["frozen_files"].items():
            if sha((self.project / path).read_bytes()) != digest:
                raise ValueError("Frozen source/input changed: " + path)
        for path, digest in read(self.base / "parent-integrity.json")["files"].items():
            if sha((self.project / path).read_bytes()) != digest:
                raise ValueError("Prior scientific evidence changed")
        if read(self.ledger_path)[:len(self.launch)] != self.launch:
            raise ValueError("Historical ledger prefix differs")

    def authorize(self):
        # A concrete frozen quote and complete offline checks precede this file.
        # The agent writes it only AFTER an explicit user budget confirmation.
        auth = read(self.base / "budget-authorization.json")
        if (auth.get("protocol_sha256") != self.digest or auth.get("quote_sha256") != sha((self.base / "cost-quote.json").read_bytes())
                or auth.get("new_cap_rub") != "400" or auth.get("explicit_user_confirmation") is not True
                or not auth.get("user_instruction")):
            raise ValueError("Separate explicit budget authorization missing or mismatched")
        deadline = datetime.fromisoformat(self.protocol["execution"]["dispatch_deadline_utc"])
        if datetime.now(timezone.utc) >= deadline:
            raise ValueError("Frozen dispatch deadline passed")
        self.key = parse_env(self.project / ".env").get("ROUTERAI_API_KEY")
        if not self.key:
            raise ValueError("RouterAI credential absent")

    def ledger(self):
        ledger = Ledger(self.ledger_path, self.cap)
        if ledger.rows[:len(self.launch)] != self.launch:
            raise ValueError("Historical budget rows changed")
        if any(not Decimal(r["charged_or_reserved_rub"]).is_finite() or Decimal(r["charged_or_reserved_rub"]) < 0 for r in ledger.rows):
            raise ValueError("Invalid budget obligation")
        if ledger.committed > self.cap:
            raise ValueError("Budget cap exceeded")
        return ledger

    def attempt(self, cell):
        from cross_model.common import canonical
        identity = sha(canonical([self.digest, cell["model"], cell["condition"], cell["item_id"]]))
        directory = self.scope / "calls" / identity
        status = {k: cell[k] for k in ("model", "provider", "condition", "item_id")}
        status["call_id"] = identity
        with self.locked():
            if directory.exists():
                result_path = directory / "result.json"
                if result_path.exists():
                    result = read(result_path)
                    if sha((directory / "request.json").read_bytes()) != result["request_sha256"] or sha((directory / "response.json").read_bytes()) != result["response_sha256"]:
                        raise ValueError("Cached raw call differs")
                    if read(directory / "request.json") != cell["request"] or any(result.get(k) != v for k, v in status.items()):
                        raise ValueError("Cached attempt identity differs")
                    parsed = validate_envelope(read(directory / "response.json"), self.items[cell["item_id"]], cell["model"], cell["provider"])
                    if any(result.get(k) != v for k, v in parsed.items()):
                        raise ValueError("Cached annotation differs from raw response")
                    return result
                return {**status, "technical_status": "unknown", "vote": None, "invalid_reason": "previous_attempt_never_resent"}
            self.authorize()
            info = next(r for r in self.quote["routes"] if r["model"] == cell["model"])
            price = (Decimal(info["prompt_rub_per_token_ceiling"]), Decimal(info["completion_rub_per_token_ceiling"]))
            reserve = estimate(cell["request"], price)
            directory.mkdir(parents=True, exist_ok=False)
            immutable(directory / "request.json", cell["request"])
            immutable(directory / "intent.json", {**status, "started_utc": utcnow(), "protocol_sha256": self.digest})
            ledger = self.ledger()
            row = ledger.reserve(reserve, "cross-model:" + self.digest + ":" + identity)
            immutable(directory / "reservation.json", row)
        try:
            response = self.transport("/chat/completions", key=self.key, body=cell["request"], timeout=90)
        except Exception as exc:
            response = {"http_status": None, "network_error": type(exc).__name__, "json": {}}
        # Redact reflected credentials, including header values, before ANY write.
        from stage0.runner import redact
        response = json.loads(redact(canonical(response).decode("utf-8"), self.key))
        immutable(directory / "response.json", response)
        validation = validate_envelope(response, self.items[cell["item_id"]], cell["model"], cell["provider"])
        payload = response.get("json") if type(response.get("json")) is dict else {}
        result = {**status, **validation, "finished_utc": utcnow(), "protocol_sha256": self.digest,
            "request_sha256": sha((directory / "request.json").read_bytes()), "response_sha256": sha((directory / "response.json").read_bytes()),
            "reservation_id": row["id"], "http_status": response.get("http_status"), "usage": payload.get("usage")}
        # Malformed usage must not break accounting or release reservations.
        accounting = response
        if type(response.get("json")) is not dict:
            accounting = {**response, "json": {}}
        elif type(response["json"].get("usage")) not in (dict, type(None)):
            accounting = {**response, "json": {**response["json"], "usage": {}}}
        with self.locked():
            ledger = self.ledger()
            retained = next(r for r in ledger.rows if r["id"] == row["id"])
            try:
                ledger.finish(retained, accounting)
            finally:
                immutable(directory / "result.json", result)
        return result

    def collect(self):
        self.authorize()
        self.verify_frozen()
        self.scope.mkdir(parents=True, exist_ok=True)
        lease = self.scope / "collector.lock"
        fd = os.open(lease, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            # Fresh free metadata before ANY paid call; fail closed if route
            # disappeared, capabilities changed, or ceiling rates increased.
            for model, provider in ROUTES:
                receipt = self.transport("/models/" + model + "/endpoints", timeout=30)
                from cross_model.common import canonical
                immutable(self.scope / "launch-metadata" / (model.replace("/", "_") + "-" + sha(canonical(receipt)) + ".json"), receipt)
                quoted = next(r for r in self.quote["routes"] if r["model"] == model)
                price = ceiling_rates(receipt, provider)
                if price[0] > Decimal(quoted["prompt_rub_per_token_ceiling"]) or price[1] > Decimal(quoted["completion_rub_per_token_ceiling"]):
                    raise ValueError("Live quote increased; no calls dispatched")
                endpoints = [e for e in receipt["json"]["data"]["endpoints"] if e["provider_name"] == provider]
                required = {"structured_outputs", "response_format", "seed", "max_tokens", "temperature", "top_p", "reasoning", "include_reasoning"}
                from stage0.runner import encode
                bound = max(len(encode(c["request"])) + 2048 + c["request"]["max_tokens"] for c in self.roster if c["model"] == model)
                if not endpoints or any(e.get("status") != 0 or not required <= set(e.get("supported_parameters", []))
                                        or e.get("context_length", 0) < bound or e.get("max_completion_tokens", 0) < 4096 for e in endpoints):
                    raise ValueError("Live structured-output route unavailable")
            collected = []
            for model, provider in ROUTES:
                route_cells = [c for c in self.roster if c["model"] == model]
                probe = self.attempt(route_cells[0])
                collected.append(probe)
                if probe["technical_status"] != "valid":
                    collected.extend({**{k:c[k] for k in ("model", "provider", "condition", "item_id")}, "technical_status": "not_dispatched_probe_failed", "vote": None} for c in route_cells[1:])
                    continue
                # Fixed list, one attempt per cell, no failed-case repair and no
                # semantic repeats. Two workers share the original OS budget lock.
                with ThreadPoolExecutor(max_workers=2) as pool:
                    for index, result in enumerate(pool.map(self.attempt, route_cells[1:]), 1):
                        collected.append(result)
                        write(self.base / "run-progress.json", {"model": model, "completed": index, "total": len(route_cells)-1, "utc": utcnow()})
            write(self.base / "new-annotations.json", {"protocol_sha256": self.digest, "completed_utc": utcnow(), "cells": collected})
            with self.locked():
                ledger = self.ledger()
                write(self.base / "ledger-final.json", ledger.rows)
                write(self.base / "budget-final.json", {"launch_rub": str(self.launch_amount), "charged_or_reserved_rub": str(ledger.committed),
                    "additional_charged_or_reserved_rub": str(ledger.committed-self.launch_amount), "cap_additional_rub": "400",
                    "ledger_rows": len(ledger.rows), "reported_new_cost_rub": str(sum((Decimal(r["reported_cost_rub"]) for r in ledger.rows[len(self.launch):] if r.get("reported_cost_rub") is not None), Decimal(0)))})
            return collected
        finally:
            lease.unlink(missing_ok=True)

    def export(self):
        """Recover fixed roster offline, preserving missing/unknown cells and raw bytes."""
        import shutil
        from cross_model.common import canonical
        collected = []
        for cell in self.roster:
            identity = sha(canonical([self.digest, cell["model"], cell["condition"], cell["item_id"]]))
            directory = self.scope / "calls" / identity
            status = {k: cell[k] for k in ("model", "provider", "condition", "item_id")}
            if directory.is_dir():
                if (directory / "result.json").is_file():
                    result = read(directory / "result.json")
                    if read(directory / "request.json") != cell["request"]:
                        raise ValueError("Exported request differs from fixed roster")
                    parsed = validate_envelope(read(directory / "response.json"), self.items[cell["item_id"]], cell["model"], cell["provider"])
                    if any(result.get(k) != v for k, v in parsed.items()):
                        raise ValueError("Exported annotation differs from raw response")
                    collected.append(result)
                else:
                    collected.append({**status, "call_id": identity, "technical_status": "unknown", "vote": None, "invalid_reason": "attempt_without_finalized_result_never_resent"})
                target = self.base / "raw" / identity
                target.mkdir(parents=True, exist_ok=True)
                for source in directory.glob("*.json"):
                    if (target / source.name).exists() and (target / source.name).read_bytes() != source.read_bytes():
                        raise ValueError("Exported raw call changed")
                    shutil.copyfile(source, target / source.name)
            else:
                collected.append({**status, "technical_status": "not_dispatched", "vote": None})
        write(self.base / "new-annotations.json", {"protocol_sha256": self.digest, "cells": collected,
            "export_scope": "fixed complete roster; no network or credential; pending reservations retained"})
        with self.locked():
            ledger = self.ledger()
            write(self.base / "ledger-final.json", ledger.rows)
            write(self.base / "budget-final.json", {"launch_rub": str(self.launch_amount), "charged_or_reserved_rub": str(ledger.committed),
                "additional_charged_or_reserved_rub": str(ledger.committed-self.launch_amount), "cap_additional_rub": "400",
                "ledger_rows": len(ledger.rows), "reported_new_cost_rub": str(sum((Decimal(r["reported_cost_rub"]) for r in ledger.rows[len(self.launch):] if r.get("reported_cost_rub") is not None), Decimal(0)))})
        return collected
