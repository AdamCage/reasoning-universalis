"""Postcollection strict-gate diagnostics; never repairs votes or dispatches calls."""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from machine_development import annotation as ann
from scripts.collect_machine_development import _MachineCore
from stage0.runner import encode
from stage2.observations import strict

VERSION = "machine-vote-failure-audit-v1"
FIELDS = {"item_id", "primary_role", "secondary_roles", "confidence", "reason_code", "evidence_quotes"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exception_chain(error):
    rows = []
    while error is not None:
        rows.append({"type": type(error).__name__, "message": str(error)})
        error = error.__cause__
    return rows


def content_diagnostics(content, item):
    """Explain failed constraints without modifying content or trying a repair."""
    try:
        value = strict(content)
    except (ValueError, TypeError, UnicodeError) as error:
        return {"strict_json": False, "exception_chain": exception_chain(error)}
    if type(value) is not dict:
        return {"strict_json": True, "json_type": type(value).__name__}
    details = {"strict_json": True, "extra_fields": sorted(set(value) - FIELDS),
               "missing_fields": sorted(FIELDS - set(value)),
               "item_identity_matches": value.get("item_id") == item["item_id"], "quotes": []}
    quotes = value.get("evidence_quotes")
    if type(quotes) is list:
        source = item["current_segment"]["text"]
        for index, quote in enumerate(quotes):
            if type(quote) is not dict:
                details["quotes"].append({"index": index, "json_type": type(quote).__name__})
                continue
            text = quote.get("quote")
            details["quotes"].append({"index": index, "fields_exact": set(quote) == {"source_id", "quote"},
                "source_id_matches": quote.get("source_id") == item["item_id"],
                "text_type": type(text).__name__, "unicode_code_points": len(text) if isinstance(text, str) else None,
                "length_within_1_to_400": isinstance(text, str) and 1 <= len(text) <= 400,
                "exact_substring_of_current_segment": isinstance(text, str) and text in source,
                "quote_utf8_sha256": ann.sha(text.encode("utf-8")) if isinstance(text, str) else None})
    return details


def classify(details, chain):
    if not details.get("strict_json"):
        return "strict_json_invalid"
    if details.get("extra_fields"):
        return "forbidden_extra_field"
    if details.get("missing_fields") or details.get("item_identity_matches") is False:
        return "schema_or_item_identity_mismatch"
    if any(row.get("length_within_1_to_400") is False for row in details.get("quotes", [])):
        return "evidence_quote_length_outside_1_to_400"
    if any(row.get("exact_substring_of_current_segment") is False for row in details.get("quotes", [])):
        return "evidence_quote_not_exact_substring"
    return "strict_schema_or_evidence_invalid"


def diagnose(response, item):
    """Apply the frozen admission conditions and expose the parser cause chain."""
    payload = response.get("json")
    checks = {"http_200": response.get("http_status") == 200,
              "network_error_absent": not response.get("network_error"),
              "decode_error_absent": not response.get("decode_error"),
              "payload_object": isinstance(payload, dict)}
    if isinstance(payload, dict):
        checks.update(api_error_absent=payload.get("error") is None,
                      model_exact=payload.get("model") == ann.MODEL,
                      provider_exact=payload.get("provider") == ann.PROVIDER)
    if not all(checks.values()):
        return {"technical_status": "invalid", "category": "transport_or_identity_invalid", "checks": checks,
                "exception_chain": [], "returned_reasoning_present": False, "vote": None}
    choices = payload.get("choices")
    complete = type(choices) is list and len(choices) == 1 and type(choices[0]) is dict
    message = choices[0].get("message") if complete else None
    message = message if isinstance(message, dict) else {}
    reasoning = bool(message.get("reasoning") or message.get("reasoning_content") or message.get("reasoning_details"))
    checks["single_choice_finished_stop"] = complete and choices[0].get("finish_reason") == "stop"
    if not checks["single_choice_finished_stop"]:
        return {"technical_status": "invalid", "category": "output_not_complete", "checks": checks,
                "exception_chain": [], "returned_reasoning_present": reasoning, "vote": None}
    content = message.get("content")
    checks["content_string"] = isinstance(content, str)
    if not checks["content_string"]:
        return {"technical_status": "invalid", "category": "content_missing", "checks": checks,
                "exception_chain": [], "returned_reasoning_present": reasoning, "vote": None}
    try:
        vote = ann.parse_response(content, item)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, UnicodeError) as error:
        chain = exception_chain(error)
        details = content_diagnostics(content, item)
        return {"technical_status": "invalid", "category": classify(details, chain), "checks": checks,
                "exception_chain": chain, "content_diagnostics": details,
                "content_utf8_sha256": ann.sha(content.encode("utf-8")),
                "returned_reasoning_present": reasoning, "vote": None}
    return {"technical_status": "valid", "category": None, "checks": checks,
            "exception_chain": [], "returned_reasoning_present": reasoning, "vote": vote}


def audit(protocol_path, output, report, *, project=ROOT, scope=None, calls=None):
    project = Path(project).resolve()
    protocol_path = Path(protocol_path).resolve()
    protocol_raw = protocol_path.read_bytes()
    protocol = strict(protocol_raw)
    protocol_digest = ann.sha(protocol_raw)
    state = project / protocol["budget"]["shared_state"]
    scope = Path(scope) if scope is not None else state / "machine-development" / protocol_digest
    calls = Path(calls) if calls is not None else state / "calls"
    input_paths = {"protocol": protocol_path, "items": project / protocol["inputs"]["path"],
                   "mapping": project / protocol["inputs"]["mapping"]["path"],
                   "codebook": project / protocol["inputs"]["codebook"]["path"],
                   "inventory": scope / "source-inventory.json", "results": scope / "results.json",
                   "plan": scope / "dispatch-plan.json"}
    raw = {name: path.read_bytes() for name, path in input_paths.items()}
    documents = {name: strict(data) for name, data in raw.items()}
    inventory = documents["inventory"]
    require(raw["protocol"] == (scope / "protocol.json").read_bytes(), "Protocol differs from frozen scope")
    require(ann.sha(raw["inventory"]) == protocol["source_freeze"]["expected_source_inventory_sha256"],
            "Prospective source inventory differs")
    for name, digest in inventory["files"].items():
        require(ann.sha((project / name).read_bytes()) == digest
                and ann.sha((scope / "source" / name).read_bytes()) == digest, "Frozen source differs: " + name)
    for name, spec in (("items", protocol["inputs"]), ("mapping", protocol["inputs"]["mapping"]),
                       ("codebook", protocol["inputs"]["codebook"])):
        require(ann.sha(raw[name]) == spec["file_sha256"]
                and raw[name] == (scope / (name + ".json")).read_bytes(), "Frozen input differs: " + name)
    items = {row["item_id"]: row for row in documents["items"]["items"]}
    result = documents["results"]
    require(result["protocol_sha256"] == protocol_digest
            and result["source_inventory_sha256"] == ann.sha(raw["inventory"])
            and result["items_sha256"] == ann.sha(raw["items"])
            and ann.sha(raw["plan"]) == result["dispatch_plan_sha256"], "Result/source binding differs")
    planned = {cell["call_id"]: cell for cell in documents["plan"]["cells"]}
    require(len(planned) == len(result["all_planned_calls"]) == result["maximum_calls"], "Roster denominator differs")
    require([row["call_id"] for row in result["all_planned_calls"]] == list(planned), "Roster order differs")
    coarse = _MachineCore.__new__(_MachineCore)
    coarse.item_lookup = items
    records, failures, status_counts, phases, categories = [], [], Counter(), Counter(), Counter()
    reasoning, mismatches = 0, []
    for saved in result["all_planned_calls"]:
        if saved["technical_status"] not in ("valid", "invalid"):
            continue
        call_id = saved["call_id"]
        cell = planned[call_id]
        directory = calls / call_id
        request_raw, response_raw = (directory / "request.json").read_bytes(), (directory / "response.json").read_bytes()
        response = strict(response_raw)
        original = strict((directory / "result.json").read_bytes())
        frozen_vote = strict((scope / "votes" / (call_id + ".json")).read_bytes())
        require(ann.sha(request_raw) == cell["request_sha256"] == saved["request_sha256"] == original["request_sha256"]
                and ann.sha(response_raw) == saved["response_sha256"] == original["response_sha256"]
                and response == original["response"] and frozen_vote == saved, "Raw vote binding differs: " + call_id)
        expected_body = ann.request_body(items[cell["item_id"]], documents["codebook"], cell["round_number"], cell["vote_index"])
        require(request_raw == encode(expected_body), "Frozen prompt/request differs: " + call_id)
        body = base64.b64decode(response["body_base64"], validate=True)
        require(ann.sha(body) == response["body_sha256"] and strict(body) == response["json"], "Raw envelope differs: " + call_id)
        diagnostic = diagnose(response, items[cell["item_id"]])
        same = diagnostic["technical_status"] == saved["technical_status"] and diagnostic["vote"] == saved["vote"]
        same = same and diagnostic["returned_reasoning_present"] == saved["returned_reasoning_present"]
        same = same and coarse._parsed(cell, original) == saved
        if not same:
            mismatches.append(call_id)
        phase = "audit" if cell["audit"] else "round" + str(cell["round_number"])
        status_counts[diagnostic["technical_status"]] += 1
        phases[phase + ":" + diagnostic["technical_status"]] += 1
        reasoning += diagnostic["returned_reasoning_present"]
        record = {"call_id": call_id, "item_id": cell["item_id"], "root_id": documents["mapping"]["items"][cell["item_id"]]["root_id"],
                  "phase": phase, "vote_index": cell["vote_index"], "request_sha256": ann.sha(request_raw),
                  "response_sha256": ann.sha(response_raw), "response_body_sha256": response["body_sha256"],
                  "technical_status": diagnostic["technical_status"], "saved_outcome_exact": same}
        records.append(record)
        if diagnostic["technical_status"] == "invalid":
            categories[diagnostic["category"]] += 1
            failures.append({**record, **{key: value for key, value in diagnostic.items() if key != "vote"}})
    require(not mismatches, "Frozen outcome mismatch: " + ",".join(mismatches))
    require(all(path.read_bytes() == raw[name] for name, path in input_paths.items()), "Input changed during audit")
    document = {"schema_version": 1, "version": VERSION, "status": "passed", "protocol_sha256": protocol_digest,
        "checker_sha256": ann.sha(Path(__file__).read_bytes()), "input_sha256": {name: ann.sha(data) for name, data in raw.items()},
        "planned_slots": result["maximum_calls"], "checked_physical_calls": len(records),
        "technical_status_counts": dict(sorted(status_counts.items())), "phase_status_counts": dict(sorted(phases.items())),
        "invalid_category_counts": dict(sorted(categories.items())), "saved_outcome_mismatches": mismatches,
        "returned_reasoning_flag_count": reasoning, "effective_reasoning_mode": "not_independently_confirmed",
        "attempts": records, "invalid_attempts": failures, "primary_labels_modified": False,
        "scientific_validity": "not_assessed", "human_gold": "not_created", "E0": "not_passed",
        "scope": "Postcollection explanation of frozen technical gates; no repaired outputs, semantic role judging or accuracy estimate"}
    lines = ["# Machine vote technical-failure audit", "", "Postcollection scripted diagnostics of the closed annotation condition. No API calls, output repair or label changes.", "",
        f"All **{len(records)} physical calls** were checked against the unchanged frozen collector gate and content parser: **{status_counts['valid']} valid / {status_counts['invalid']} invalid**, with **{len(mismatches)} disagreements** with stored outcomes. The finite registry retains {result['maximum_calls']} maximum slots; conditional unscheduled slots are not physical attempts.", "",
        f"Returned-reasoning flags: **{reasoning}**. This describes returned fields only; effective internal mode remains unconfirmed.", "",
        "| Exact diagnostic category | Invalid calls |", "|---|---:|"]
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(categories.items()))
    lines += ["", "All six observed failures were first-round HTTP 200 responses with the exact requested model/provider and `finish_reason=stop`. Two added a forbidden `reason_code_note` field. Four supplied an exact source substring longer than the permitted 400 Unicode code points (445, 445, 445 and 446). The inherited parser's combined message `Quote not present in supplied current source` therefore denotes the quote-length constraint in these four cases; it does not establish a fabricated quote.", "",
        "| Call ID | Item ID | Diagnostic |", "|---|---|---|"]
    lines.extend(f"| `{row['call_id']}` | `{row['item_id']}` | `{row['category']}` |" for row in failures)
    lines += ["", "The [machine-readable audit](../artifacts/machine-annotation-development-2026-11-08/failure-audit.json) records all checked call IDs and request/response/body hashes; invalid rows also retain original root IDs, parser exception chains, extra/missing fields and quote-length/exact-substring checks. These details explain technical exclusion, not the correctness of an accepted functional label. Six invalid votes still leave three primary items technically unresolved; neither their JSON nor consensus was repaired.", "",
        f"Frozen protocol SHA-256: `{protocol_digest}`. Source inventory SHA-256: `{ann.sha(raw['inventory'])}`. Audit script SHA-256: `{document['checker_sha256']}`.", "",
        "Human gold remains absent; E0 is not passed and scientific validity is not assessed.", ""]
    output, report = Path(output), Path(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encode(document))
    report.write_text("\n".join(lines), encoding="utf-8")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--calls", type=Path)
    args = parser.parse_args()
    result = audit(args.protocol, args.output, args.report, project=args.project, scope=args.scope, calls=args.calls)
    print(json.dumps({key: result[key] for key in ("status", "checked_physical_calls", "technical_status_counts", "invalid_category_counts", "returned_reasoning_flag_count")}))


if __name__ == "__main__":
    main()
