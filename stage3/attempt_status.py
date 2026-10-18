"""Derive attempt status from the raw response and reject a contradictory label."""
from stage0.traces import inspect_trace


def derive_status(http_status, body):
    if http_status != 200 or not isinstance(body, dict) or body.get("error") is not None:
        return "failed"
    if not isinstance(body.get("id"), str) or not body["id"]:
        return "failed"
    observed = inspect_trace(body)
    if observed["status"] == "visible_trace_candidate":
        return "completed"
    if observed["trace"] or observed["answer"] or observed["status"] in {
            "summary_or_truncated_or_unfinished", "summary_only", "encrypted_only", "answer_only"}:
        return "incomplete"
    return "failed"


def assert_status_matches(record, http_status, body):
    expected = derive_status(http_status, body)
    if record.get("status") != expected:
        raise ValueError("Recorded status " + str(record.get("status")) + " disagrees with raw status " + expected)
    return expected
