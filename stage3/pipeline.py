"""Stage 3 attempt path. Stage 2 files are not the pilot dispatcher.

A call reserves on the shared ledger and journals the raw request before the
transport runs. HTTP status is read from the transport response. Models and
providers enter only through the positive allowlist.
"""
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

from stage0.runner import Ledger, StopRun, estimate
from stage2.observations import ObservationStore, canonical
from stage3.attempt_status import assert_status_matches, derive_status
from stage3.bindings import align_embeddings
from stage3.schedule import bind_response, freeze_attempt

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "design" / "ADMITTED_ROUTES.json"
PUBLISHED_LEDGER_SHA = "e062d9bdd228933ddcca0047d9ee15e564b82413bf88f92c5d06550c9febb88d"
PUBLISHED_LEDGER_MEMBER = "evidence/stage0-budget.json"
PUBLISHED_ARCHIVE = ROOT / "evidence" / "stage0-2026-10-12.zip"
PUBLISHED_CAP_RUB = Decimal("900")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_published_ledger():
    import zipfile
    with zipfile.ZipFile(PUBLISHED_ARCHIVE) as bundle:
        data = bundle.read(PUBLISHED_LEDGER_MEMBER)
    if sha256(data) != PUBLISHED_LEDGER_SHA:
        raise ValueError("Published Stage 0 ledger bytes changed")
    rows = json.loads(data)
    charged = sum((Decimal(row["charged_or_reserved_rub"]) for row in rows), Decimal(0))
    return {"rows": len(rows), "charged_or_reserved_rub": str(charged),
            "sha256": PUBLISHED_LEDGER_SHA, "cap_rub": str(PUBLISHED_CAP_RUB),
            "remaining_rub": str(PUBLISHED_CAP_RUB - charged)}


def load_allowlist(path=ALLOWLIST_PATH):
    document = json.loads(Path(path).read_bytes())
    routes = {}
    for route in document["routes"]:
        if route.get("admitted") is not True:
            continue
        routes[(route["model_id"], route["provider_id"], route["purpose"])] = route
    return routes


def _price(prompt_per_token, completion_per_token):
    price = (Decimal(str(prompt_per_token)), Decimal(str(completion_per_token)))
    if any(not item.is_finite() or item < 0 or item >= 1 for item in price):
        raise ValueError("Price must be a non-negative rub-per-token amount below 1")
    return price


def execute_attempt(*, model_id, task_id, sample_index, seed, provider_id, protocol_digest,
                    task_prompt, transport, ledger_path, journal_root, cap_rub,
                    prompt_per_token, completion_per_token, purpose, expected_ledger_sha256,
                    allowlist_path=ALLOWLIST_PATH, claimed_status=None, mass_pilot=False,
                    max_tokens=4096):
    if mass_pilot:
        raise ValueError("Mass pilot is not authorized")
    ledger_path = Path(ledger_path)
    journal_root = Path(journal_root)
    snapshot = ledger_path.read_bytes()
    if sha256(snapshot) != expected_ledger_sha256:
        raise ValueError("Shared ledger does not match the approved snapshot")
    if not snapshot.strip():
        raise ValueError("Empty ledger cannot reset historical reservations")
    allowlist = load_allowlist(allowlist_path)
    if allowlist.get((model_id, provider_id, purpose)) is None:
        raise ValueError("Model/provider is not on the positive admission list for this purpose")
    spec = freeze_attempt(model_id=model_id, task_id=task_id, sample_index=sample_index, seed=seed,
                          provider_id=provider_id, protocol_digest=protocol_digest)
    request = {"model": spec["model_id"], "seed": spec["seed"], "max_tokens": max_tokens,
               "messages": [{"role": "user", "content": task_prompt}]}
    price = _price(prompt_per_token, completion_per_token)
    journal_root.mkdir(parents=True, exist_ok=True)
    lock = journal_root / "dispatch.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise StopRun("Budget lock exists; reconcile unknown attempts first") from None
    os.close(descriptor)
    journal = ObservationStore(journal_root / "raw")
    try:
        if sha256(ledger_path.read_bytes()) != expected_ledger_sha256:
            raise ValueError("Shared ledger changed before reservation")
        ledger = Ledger(ledger_path, Decimal(str(cap_rub)))
        reservation = ledger.reserve(estimate(request, price), "stage3:" + purpose + ":" + model_id)
        request_key = journal.put(canonical(request))
        journal.json({"phase": "reserved", "reservation_id": reservation["id"], "request_digest": request_key,
                      "model_id": model_id, "provider_id": provider_id, "task_id": task_id,
                      "sample_index": sample_index, "seed": seed})
        try:
            response = transport(request)
        except Exception:
            journal.json({"phase": "transport_failed", "reservation_id": reservation["id"],
                          "request_digest": request_key})
            raise
        if not isinstance(response, dict) or "json" not in response:
            journal.json({"phase": "malformed_response", "reservation_id": reservation["id"],
                          "request_digest": request_key})
            raise ValueError("Transport returned no response body")
        http_status = response.get("http_status")
        if type(http_status) is not int:
            journal.json({"phase": "missing_http_status", "reservation_id": reservation["id"],
                          "request_digest": request_key})
            raise ValueError("HTTP status must come from the transport response")
        safe = {key: value for key, value in response.items() if key != "headers"}
        response_key = journal.json(safe)
        ledger.finish(reservation, safe)
        journal.json({"phase": "finished_or_unknown", "reservation_id": reservation["id"],
                      "request_digest": request_key, "response_digest": response_key, "http_status": http_status})
        bind_response(spec, request, safe)
        body = safe["json"]
        derived = derive_status(http_status, body)
        record = {"status": derived, "http_status": http_status, "model_id": spec["model_id"],
                  "provider_id": spec["provider_id"], "task_id": spec["task_id"],
                  "sample_index": spec["sample_index"], "seed": spec["seed"],
                  "protocol_digest": spec["protocol_digest"], "analysis_usable": derived == "completed",
                  "request_digest": request_key, "response_digest": response_key,
                  "ledger_sha256": sha256(ledger_path.read_bytes()), "reservation_id": reservation["id"]}
        if claimed_status is not None:
            assert_status_matches({"status": claimed_status}, http_status, body)
        assert_status_matches(record, http_status, body)
        return record
    finally:
        lock.unlink(missing_ok=True)


def accept_embeddings(rows, records, model_id, dimension, context_mode):
    return align_embeddings(rows, records, model_id, dimension, context_mode)
