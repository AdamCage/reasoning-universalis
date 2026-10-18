"""Stage 3 attempt path. Guards run here; Stage 2 modules are not the pilot dispatcher.

No network call is made unless the caller supplies a transport, and only after
admission and ledger checks. Mass pilot remains unauthorized: pass mass_pilot=False.
"""
from stage3.attempt_status import assert_status_matches, derive_status
from stage3.bindings import align_embeddings
from stage3.schedule import bind_response, freeze_attempt


def execute_attempt(*, model_id, task_id, sample_index, seed, provider_id, protocol_digest,
                    task_prompt, transport, http_status, ledger_sha256, claimed_status=None,
                    mass_pilot=False):
    if mass_pilot:
        raise ValueError("Mass pilot is not authorized")
    if not isinstance(ledger_sha256, str) or len(ledger_sha256) != 64:
        raise ValueError("Reconciled ledger snapshot is required before dispatch")
    spec = freeze_attempt(model_id=model_id, task_id=task_id, sample_index=sample_index, seed=seed,
                          provider_id=provider_id, protocol_digest=protocol_digest)
    if not spec["admitted_for_dispatch"]:
        raise ValueError("Model is not admitted for dispatch")
    request = {"model": spec["model_id"], "seed": spec["seed"],
               "messages": [{"role": "user", "content": task_prompt}]}
    response = transport(request)
    if not isinstance(response, dict) or "json" not in response:
        raise ValueError("Transport returned no response body")
    bind_response(spec, request, response)
    body = response["json"]
    derived = derive_status(http_status, body)
    record = {"status": derived, "model_id": spec["model_id"], "task_id": spec["task_id"],
              "sample_index": spec["sample_index"], "seed": spec["seed"], "provider_id": spec["provider_id"],
              "protocol_digest": spec["protocol_digest"], "analysis_usable": derived == "completed",
              "ledger_sha256": ledger_sha256}
    if claimed_status is not None:
        assert_status_matches({"status": claimed_status}, http_status, body)
    assert_status_matches(record, http_status, body)
    return record


def accept_embeddings(rows, records, model_id, dimension, context_mode):
    return align_embeddings(rows, records, model_id, dimension, context_mode)
