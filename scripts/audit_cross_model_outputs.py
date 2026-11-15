"""Diagnose output-contract failures without repairing or reclassifying votes.

Only already-exported public requests, responses and annotations are read.
The frozen parser remains the sole source of local validity. JSON Schema
validation is an independent diagnostic, never an admission rule or label rescue.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cross_model.annotation import parse_response, validate_envelope

try:
    from jsonschema import Draft202012Validator
    JSONSCHEMA_VERSION = importlib.metadata.version("jsonschema")
except ImportError:
    Draft202012Validator, JSONSCHEMA_VERSION = None, None

ARTIFACT = "artifacts/cross-model-compat-2026-11-15"
PROTOCOL = "design/CROSS_MODEL_TRANSPORT_ADDENDUM_2026_11_15.json"
PARENT = "artifacts/machine-annotation-development-2026-11-08"


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def schema_check(value, schema):
    if Draft202012Validator is None:
        return None, []
    errors = sorted(Draft202012Validator(schema).iter_errors(value),
                    key=lambda error: (str(list(error.absolute_path)), error.validator, error.message))
    return not errors, [{"path": list(error.absolute_path), "keyword": error.validator,
                         "schema_path": list(error.absolute_schema_path)} for error in errors]


def classify(content, item, schema=None):
    """Return diagnostics about the exact content; invalid votes stay null.

    Duplicate keys/nonfinite values are detected during decoding and block all
    schema diagnostics on the decoded object. No fence stripping, replacement,
    whitespace normalization, duplicate removal, or fallback label is performed.
    """
    if schema is None:
        schema = read(ROOT / PARENT / "codebook.json")["response_schema"]
    failures, duplicate_keys, nonfinite = [], [], []
    value, syntax_valid = None, False
    if not isinstance(content, str):
        failures.append("content_not_string")
    else:
        if content.lstrip().startswith("```"):
            failures.append("markdown_fence")
        def unique(pairs):
            decoded = {}
            for key, entry in pairs:
                if key in decoded:
                    duplicate_keys.append(key)
                decoded[key] = entry
            return decoded
        def finite(token):
            nonfinite.append(token)
            return None
        try:
            value = json.loads(content, object_pairs_hook=unique, parse_constant=finite)
            syntax_valid = True
        except (ValueError, TypeError, UnicodeError):
            failures.append("json_syntax")
    if duplicate_keys:
        failures.append("json_duplicate_key")
    if nonfinite:
        failures.append("json_nonfinite")
    strict_valid = syntax_valid and not duplicate_keys and not nonfinite
    supplied_valid, supplied_errors = (schema_check(value, schema) if strict_valid else (None, []))
    current = item["current_segment"]["text"]
    previous = "".join(segment["text"] for segment in item.get("previous_segments", []))
    problem = item.get("problem_statement", "")
    quotes = {"total": 0, "current_exact": 0, "context_only": 0, "problem_only": 0,
              "neither_current_context_nor_problem": 0}
    if strict_valid:
        if type(value) is not dict:
            failures.append("schema_top_level_not_object")
        else:
            required = {"item_id", "primary_role", "secondary_roles", "confidence", "reason_code", "evidence_quotes"}
            if required - set(value):
                failures.append("schema_missing_required")
            if set(value) - required:
                failures.append("schema_additional_properties")
            if value.get("item_id") != item["item_id"]:
                failures.append("item_id_mismatch")
            properties = schema.get("properties", {})
            primary = value.get("primary_role")
            if primary not in properties.get("primary_role", {}).get("enum", []):
                failures.append("primary_role_enum")
            secondary = value.get("secondary_roles")
            if type(secondary) is not list:
                failures.append("secondary_roles_type")
            else:
                if len(secondary) > 3:
                    failures.append("secondary_too_many")
                if any(v not in properties.get("secondary_roles", {}).get("items", {}).get("enum", []) for v in secondary):
                    failures.append("secondary_roles_enum")
                if any(v == primary for v in secondary):
                    failures.append("secondary_contains_primary")
                serial = [json.dumps(v, sort_keys=True, allow_nan=False) for v in secondary]
                if len(serial) != len(set(serial)):
                    failures.append("secondary_duplicate")
            for field, code in (("confidence", "confidence_enum"), ("reason_code", "reason_code_enum")):
                if value.get(field) not in properties.get(field, {}).get("enum", []):
                    failures.append(code)
            evidence = value.get("evidence_quotes")
            if type(evidence) is not list:
                failures.append("evidence_quotes_type")
            else:
                if not 1 <= len(evidence) <= 3:
                    failures.append("evidence_quotes_count")
                for entry in evidence:
                    quotes["total"] += 1
                    if type(entry) is not dict:
                        failures.append("evidence_object_schema")
                        continue
                    if set(entry) != {"source_id", "quote"}:
                        failures.append("evidence_object_schema")
                    if entry.get("source_id") != item["item_id"]:
                        failures.append("evidence_source_mismatch")
                    quote = entry.get("quote")
                    if not isinstance(quote, str):
                        failures.append("evidence_quote_type")
                        continue
                    if not quote:
                        failures.append("evidence_quote_empty")
                        continue
                    if len(quote) > 400:
                        failures.append("evidence_quote_too_long")
                    if quote in current:
                        quotes["current_exact"] += 1
                    else:
                        failures.append("evidence_quote_not_current")
                        if quote in previous:
                            failures.append("evidence_quote_context_only")
                            quotes["context_only"] += 1
                        elif quote in problem:
                            failures.append("evidence_quote_problem_only")
                            quotes["problem_only"] += 1
                        else:
                            quotes["neither_current_context_nor_problem"] += 1
    try:
        local_vote = parse_response(content, item)
        local_valid = True
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, UnicodeError):
        local_vote, local_valid = None, False
    return {"strict_json_valid": strict_valid, "json_syntax_decoded": syntax_valid,
            "duplicate_keys": sorted(set(duplicate_keys)), "nonfinite_literals": sorted(set(nonfinite)),
            "supplied_schema_valid": supplied_valid, "supplied_schema_errors": supplied_errors,
            "local_parser_valid": local_valid, "local_vote": local_vote,
            "schema_parser_mismatch": supplied_valid is not None and supplied_valid != local_valid,
            "failures": sorted(set(failures)), "quote_locations": quotes}


def envelope_failures(response, model, provider):
    codes = []
    if response.get("http_status") != 200:
        codes.append("http_status_not_200")
    if response.get("network_error"):
        codes.append("network_error")
    payload = response.get("json")
    if type(payload) is not dict:
        return codes + ["response_json_not_object"], {}, {}, None
    if payload.get("error") is not None:
        codes.append("api_error")
    if payload.get("model") != model:
        codes.append("returned_model_mismatch")
    if payload.get("provider") != provider:
        codes.append("returned_provider_mismatch")
    choices = payload.get("choices")
    if type(choices) is not list or len(choices) != 1:
        return codes + ["choices_count_or_type"], payload, {}, None
    if type(choices[0]) is not dict:
        return codes + ["choice_not_object"], payload, {}, None
    finish = choices[0].get("finish_reason")
    if finish != "stop":
        codes.append("finish_reason_not_stop")
    message = choices[0].get("message")
    if type(message) is not dict:
        return codes + ["message_not_object"], payload, {}, finish
    return codes, payload, message, finish


def build(project=ROOT, output=None):
    project = Path(project).resolve(strict=True)
    base = project / ARTIFACT
    protocol_path = project / PROTOCOL
    protocol_raw, protocol = protocol_path.read_bytes(), read(protocol_path)
    annotations_path = base / "new-annotations.json"
    annotations = read(annotations_path)
    require(annotations["protocol_sha256"] == sha(protocol_raw), "Annotation protocol hash differs")
    # These bytes include all measured/frozen artifacts plus derived summaries;
    # the audit may add its own two outputs and may never rewrite an input.
    protected = dict(protocol["frozen_files"])
    protected[PROTOCOL] = sha(protocol_raw)
    for path in base.rglob("*"):
        if path.is_file() and path.name not in ("output-contract-audit.json", "output-contract-audit.csv"):
            protected[path.relative_to(project).as_posix()] = sha(path.read_bytes())
    for name, expected in protected.items():
        require(sha((project / name).read_bytes()) == expected, "Frozen or measured input changed before audit")
    items = {item["item_id"]: item for item in read(base / "input-items.json")["items"]}
    rows = []
    for cell in annotations["cells"]:
        require("call_id" in cell, "Audit expects exported attempted cells with raw identities")
        directory = base / "raw" / cell["call_id"]
        request_path, response_path = directory / "request.json", directory / "response.json"
        request_raw, response_raw = request_path.read_bytes(), response_path.read_bytes()
        require(sha(request_raw) == cell["request_sha256"] and sha(response_raw) == cell["response_sha256"],
                "Raw request/response hash differs")
        request, response = json.loads(request_raw), json.loads(response_raw)
        prompt = json.loads(request["messages"][1]["content"])
        original = copy.deepcopy(items[cell["item_id"]])
        if cell["condition"] == "without_context":
            original["previous_segments"] = []
        require(prompt["item_id"] == original["item_id"] and prompt["current_segment"] == original["current_segment"]
                and prompt["problem_statement"] == original["problem_statement"]
                and prompt["previous_segments"] == (["".join(p["text"] for p in original["previous_segments"])] if original["previous_segments"] else []),
                "Raw prompt differs from original current segment or allowed context")
        envelope_codes, payload, message, finish = envelope_failures(response, cell["model"], cell["provider"])
        content = message.get("content")
        diagnostic = classify(content, original, prompt["response_schema"])
        transport_valid, transport_errors = (schema_check(json.loads(content), request["response_format"]["json_schema"]["schema"])
            if diagnostic["strict_json_valid"] else (None, []))
        replay = validate_envelope(response, original, cell["model"], cell["provider"])
        usage = payload.get("usage") if type(payload.get("usage")) is dict else {}
        details = usage.get("completion_tokens_details") if type(usage.get("completion_tokens_details")) is dict else {}
        reasoning_tokens = details.get("reasoning_tokens")
        reasoning_tokens = reasoning_tokens if type(reasoning_tokens) is int and reasoning_tokens >= 0 else None
        completion_tokens = usage.get("completion_tokens")
        completion_tokens = completion_tokens if type(completion_tokens) is int and completion_tokens >= 0 else None
        diagnostic.pop("local_vote")
        rows.append({"call_id": cell["call_id"], "item_id": cell["item_id"], "model": cell["model"], "provider": cell["provider"],
            "condition": cell["condition"], "primary_status": cell["technical_status"],
            "replayed_status": replay["technical_status"], "status_matches_record": replay["technical_status"] == cell["technical_status"],
            "stored_vote_matches_replay": replay["vote"] == cell.get("vote"),
            "http_status": response.get("http_status"), "finish_reason": finish,
            "envelope_failures": envelope_codes, "failures": sorted(set(envelope_codes + diagnostic["failures"])),
            **{k:v for k,v in diagnostic.items() if k != "failures"},
            "transport_schema_valid": transport_valid, "transport_schema_errors": transport_errors,
            "requested_reasoning": request.get("reasoning"), "requested_include_reasoning": request.get("include_reasoning"),
            "returned_reasoning_text_flag": bool(message.get("reasoning") or message.get("reasoning_content") or message.get("reasoning_details")),
            "reasoning_tokens_reported": reasoning_tokens, "completion_tokens_reported": completion_tokens,
            "request_sha256": sha(request_raw), "response_sha256": sha(response_raw),
            "content_characters": len(content) if isinstance(content, str) else None,
            "current_text_sha256": sha(original["current_segment"]["text"].encode("utf-8"))})
    groups = defaultdict(list)
    for row in rows:
        groups[row["model"] + "|" + row["condition"]].append(row)
    summaries = {}
    for name, values in sorted(groups.items()):
        summaries[name] = {"calls": len(values), "primary_status_counts": dict(Counter(r["primary_status"] for r in values)),
            "failure_call_counts": dict(sorted(Counter(code for r in values for code in r["failures"]).items())),
            "prompt_schema_valid_local_invalid": sum(r["supplied_schema_valid"] is True and not r["local_parser_valid"] for r in values),
            "transport_schema_valid_local_invalid": sum(r["transport_schema_valid"] is True and not r["local_parser_valid"] for r in values),
            "returned_reasoning_text_flag_calls": sum(r["returned_reasoning_text_flag"] for r in values),
            "reasoning_tokens_reported_calls": sum(r["reasoning_tokens_reported"] is not None for r in values),
            "reasoning_tokens_sum": sum(r["reasoning_tokens_reported"] or 0 for r in values),
            "completion_tokens_sum": sum(r["completion_tokens_reported"] or 0 for r in values),
            "requested_reasoning_enabled_calls": sum(type(r["requested_reasoning"]) is dict and r["requested_reasoning"].get("enabled") is True for r in values)}
    audit = {"schema_version": 1, "diagnostic_only": True, "labels_modified": False, "reclassification": False,
        "network_attempts": 0, "retries": 0, "protocol_sha256": sha(protocol_raw), "annotations_sha256": sha(annotations_path.read_bytes()),
        "audit_script_sha256": sha(Path(__file__).read_bytes()), "calls": len(rows),
        "primary_status_counts": dict(Counter(r["primary_status"] for r in rows)),
        "all_statuses_match_frozen_parser": all(r["status_matches_record"] and r["stored_vote_matches_replay"] for r in rows),
        "failure_call_counts": dict(sorted(Counter(code for r in rows for code in r["failures"]).items())),
        "schema_validator": {"backend": "jsonschema.Draft202012Validator" if Draft202012Validator else "unavailable",
                             "version": JSONSCHEMA_VERSION, "missing_dependency_policy": "Schema diagnostic null; frozen local parser still authoritative; no install/network"},
        "contract_facts": {"prompt_schema_forbids_primary_in_secondary": False,
            "local_parser_forbids_primary_in_secondary": True, "prompt_schema_secondary_uniqueItems": True,
            "transport_schema_secondary_uniqueItems": False,
            "evidence_literal_current_membership_is_extra_local_constraint": True,
            "reasoning_usage_does_not_prove_internal_mode": True},
        "by_model_condition": summaries, "rows": rows,
        "interpretation_boundary": "Exact output-contract diagnostics only. Rejected objects remain rejected; no annotations are repaired, recovered, replaced, or rescored."}
    target = Path(output) if output else base / "analysis/output-contract-audit.json"
    require(target.resolve() not in {(project / name).resolve() for name in protected}, "Audit cannot overwrite measured or frozen input")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    table_path = target.with_suffix(".csv")
    require(table_path.resolve() not in {(project / name).resolve() for name in protected}, "Audit CSV cannot overwrite measured input")
    fields = ("call_id", "model", "condition", "primary_status", "local_parser_valid", "supplied_schema_valid", "transport_schema_valid",
              "schema_parser_mismatch", "status_matches_record", "failures", "reasoning_tokens_reported", "returned_reasoning_text_flag")
    with table_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "|".join(row[key]) if key == "failures" else row[key] for key in fields})
    for name, expected in protected.items():
        require(sha((project / name).read_bytes()) == expected, "Frozen or measured input changed during audit")
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit = build(args.project, args.output)
    print(json.dumps({key: audit[key] for key in ("calls", "primary_status_counts", "failure_call_counts", "all_statuses_match_frozen_parser")}, sort_keys=True))


if __name__ == "__main__":
    main()
