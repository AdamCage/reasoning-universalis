"""Independent diagnostic parsing and certificate checks; never changes labels.

Run on a closed result file. The reference-certificate checker uses algorithms
separate from the primary solver. This script has its own strict answer parser
and arithmetic, topological-order and move-simulation paths. No model/API calls,
functional annotation, human review or E0 validation are performed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pilot_v2.tasks import verify_certificate

VERSION = "pilot-v2-independent-answer-audit-v1"
FROZEN_TASKS_SOURCE_SHA256 = "fc3c355ab3a58fd9bf2d8b35e4770bcf8a2126184436c55b3b13ca61b29f1a37"
MOVES = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(canonical(value))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_answer(domain, text):
    """Separate final-line parser; Boolean/float node IDs are never integers."""
    if type(text) is not str or not text.strip():
        return None, "missing_answer_text"
    final = text.strip().splitlines()[-1].strip()
    if not final.startswith("ANSWER: "):
        return None, "missing_final_answer_marker"
    payload = final[len("ANSWER: "):].strip()
    if domain == "math":
        if len(payload) > 1000 or re.fullmatch(r"[+-]?[0-9]+", payload) is None:
            return None, "expected_ascii_integer"
        return int(payload), None
    if domain == "logic":
        return (payload, None) if payload in ("SAT", "UNSAT") else (None, "expected_sat_or_unsat")
    if payload == "IMPOSSIBLE":
        return payload, None
    try:
        value = json.loads(payload)
    except (ValueError, TypeError):
        return None, "invalid_json_array"
    if type(value) is not list:
        return None, "expected_json_array"
    if domain == "algorithms":
        if any(type(node) is not int for node in value):
            return None, "node_ids_must_be_integers"
    elif domain == "planning":
        if any(type(move) is not str or move not in MOVES for move in value):
            return None, "unknown_or_nonstring_move"
    else:
        raise ValueError("Unknown audit task domain")
    return value, None


def check_task(task):
    certificate = task["reference_certificate"]
    require(task.get("reference_certificate_sha256") == digest(certificate), "Certificate digest mismatch")
    require(task.get("task_digest") == digest({k: v for k, v in task.items() if k != "task_digest"}),
            "Task digest mismatch")
    require(verify_certificate(task, certificate), "Independent reference-certificate check failed")
    return certificate


def classify(task, text, *, certificate_checked=False):
    certificate = task["reference_certificate"] if certificate_checked else check_task(task)
    domain, data = task["domain"], task["data"]
    parsed, reason = parse_answer(domain, text)
    if reason:
        return {"verdict": "unparseable", "correct": None, "parsed_answer": None, "reason": reason}
    if domain == "math":
        total = 0
        operations = {"add": lambda a, b: a + b, "sub": lambda a, b: a - b, "mul": lambda a, b: a * b}
        for track in data["tracks"]:
            current = int(track["initial"])
            for operation, operand in track["steps"]:
                current = operations[operation](current, int(operand))
            total += int(track["weight"]) * current
        require(total == certificate["answer"], "Independent arithmetic and checked certificate differ")
        correct, reason = parsed == total, "wrong_exact_integer"
    elif domain == "logic":
        # Exhaustive truth-table count/hash and witness were checked above.
        correct, reason = parsed == certificate["answer"], "contradicts_exhaustive_cnf_certificate"
    elif domain == "algorithms":
        impossible = certificate["kind"] == "directed_cycle_witness"
        if parsed == "IMPOSSIBLE":
            correct, reason = impossible, "claims_impossible_for_acyclic_graph"
        elif impossible:
            correct, reason = False, "order_proposed_for_graph_with_checked_cycle"
        elif len(parsed) != data["nodes"] or set(parsed) != set(range(data["nodes"])):
            correct, reason = False, "wrong_node_permutation"
        else:
            remaining, correct, reason = set(range(data["nodes"])), True, "verified"
            edges = set(map(tuple, data["edges"]))
            for node in parsed:
                available = sorted(candidate for candidate in remaining
                    if not any(target == candidate and source in remaining for source, target in edges))
                if node not in available:
                    correct, reason = False, "violates_directed_dependency"
                    break
                if node != available[0]:
                    correct, reason = False, "valid_but_nonlexicographic_topological_order"
                    break
                remaining.remove(node)
    else:
        impossible = certificate["answer"] == "IMPOSSIBLE"
        if parsed == "IMPOSSIBLE":
            correct, reason = impossible, "claims_impossible_despite_checked_bounded_path"
        elif len(parsed) > data["max_steps"]:
            correct, reason = False, "plan_exceeds_move_bound"
        else:
            x, y = data["start"]
            obstacles = set(map(tuple, data["obstacles"]))
            correct, reason = True, "verified"
            for move in parsed:
                dx, dy = MOVES[move]
                x, y = x + dx, y + dy
                if not (0 <= x < data["width"] and 0 <= y < data["height"]):
                    correct, reason = False, "plan_leaves_grid"
                    break
                if (x, y) in obstacles:
                    correct, reason = False, "plan_enters_obstacle"
                    break
            if correct and [x, y] != data["goal"]:
                correct, reason = False, "plan_does_not_reach_goal"
            require(not (correct and impossible), "Legal bounded path contradicts checked BFS certificate")
    return {"verdict": "correct" if correct else "incorrect", "correct": bool(correct),
            "parsed_answer": parsed, "reason": "verified" if correct else reason}


def audit_document(records, tasks):
    lookup = {task["task_id"]: task for task in tasks}
    require(len(lookup) == len(tasks), "Duplicate task identity")
    for task in tasks:
        check_task(task)
    rows, mismatches, unavailable, seen = [], [], 0, set()
    for record in records:
        task = lookup.get(record.get("task_id"))
        require(task is not None and task["root_id"] == record.get("root_id"), "Unknown task/root in result")
        require(record.get("trace_id") not in seen, "Duplicate trace identity")
        seen.add(record.get("trace_id"))
        if "raw_answer_grading" not in record and "answer" not in record:
            unavailable += 1
            continue
        diagnostic = classify(task, record.get("answer"), certificate_checked=True)
        raw = record.get("raw_answer_grading") or {}
        raw_match = diagnostic["verdict"] == raw.get("verdict") if "verdict" in raw else None
        primary_match = diagnostic["correct"] == record["correct"] if type(record.get("correct")) is bool else None
        censored = record.get("budget_censored") is True or record.get("finish_reason") == "length"
        eligibility_consistent = not (type(record.get("correct")) is bool and
            (censored or record.get("status") != "completed" or record.get("finish_reason") != "stop"
             or record.get("gradable") is not True))
        row = {key: record.get(key) for key in ("trace_id", "task_id", "root_id", "model", "provider", "output_budget_tokens", "status", "finish_reason")}
        row.update({"primary_correct_recorded": record.get("correct"), "budget_censored": censored,
            "recorded_diagnostic_verdict": raw.get("verdict"), "independent_diagnostic": diagnostic,
            "recorded_diagnostic_matches": raw_match, "recorded_primary_matches": primary_match,
            "primary_eligibility_consistent": eligibility_consistent,
            "reference_certificate_sha256": task["reference_certificate_sha256"]})
        rows.append(row)
        if raw_match is False or primary_match is False or not eligibility_consistent:
            mismatches.append(row["trace_id"])
    return {"schema_version": 1, "version": VERSION, "tasks": len(tasks), "reference_certificates_checked": len(tasks),
        "result_rows": len(records), "answer_diagnostics_checked": len(rows), "unavailable_without_answer": unavailable,
        "recorded_primary_gradeable": sum(type(r.get("correct")) is bool for r in records),
        "recorded_primary_errors": sum(r.get("correct") is False for r in records),
        "independent_diagnostic_counts": dict(Counter(row["independent_diagnostic"]["verdict"] for row in rows)),
        "unparseable_reasons": dict(Counter(row["independent_diagnostic"]["reason"] for row in rows
            if row["independent_diagnostic"]["verdict"] == "unparseable")),
        "mismatch_trace_ids": mismatches, "all_checked_recorded_labels_agree": not mismatches,
        "records_sha256": digest(records), "tasks_sha256": digest(tasks), "rows": rows,
        "label_policy": "Read-only diagnostics; original primary labels and censored/missing outcomes are never replaced",
        "limitations": "Programming-level corroboration using independent algorithms and parser; not human annotation, independent scientific review or E0 validation",
        "E0": "not_passed", "scientific_validity": "not_assessed", "review": "not_requested", "network_calls": 0}


def render_report(audit, artifact):
    errors = [row for row in audit["rows"] if row["primary_correct_recorded"] is False]
    lines = ["# Диагностический аудит ответов pilot v2", "",
        f"Проверены {audit['reference_certificates_checked']} reference certificates и {audit['answer_diagnostics_checked']} ответов/диагностик из {audit['result_rows']} строк. Primary gradeable: {audit['recorded_primary_gradeable']}; записанных primary ошибок: {audit['recorded_primary_errors']}.", "",
        f"Расхождений с сохранёнными labels/eligibility: {len(audit['mismatch_trace_ids'])}. Labels исходного коллектора не изменялись; length и missing не превращались в неверные ответы.", "",
        "Парсер ANSWER и проверки арифметики, доступных DAG-узлов и grid moves написаны отдельно. Все certificates проверены frozen независимыми Fraction/exhaustive/layer/replay алгоритмами. Это программная диагностика, не человеческая разметка, review или E0.", "",
        f"Машинный артефакт: `{artifact}`. Checker SHA-256: `{audit['checker_sha256']}`; frozen reference checker source: `{audit['reference_checker_source_sha256']}`.", ""]
    if errors:
        lines += ["| Task | Model/provider | Cap | Независимая причина |", "|---|---|---:|---|"]
        for row in errors:
            lines.append(f"| {row['task_id']} | {row['model']} / {row['provider']} | {row['output_budget_tokens']} | {row['independent_diagnostic']['reason']} |")
        lines.append("")
    lines += ["Полные сведения о каждой проверенной ошибке, unparseable diagnostics и certificate hashes сохранены в JSON. Научная валидность остаётся `not_assessed`, review — `not_requested`, E0 — `not_passed`.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    checker = ROOT / "pilot_v2/tasks.py"
    require(sha(checker.read_bytes()) == FROZEN_TASKS_SOURCE_SHA256, "Reference checker differs from frozen A/R1 source")
    record_bytes, task_bytes = args.records.read_bytes(), args.tasks.read_bytes()
    document, corpus = json.loads(record_bytes), json.loads(task_bytes)
    require(document.get("completed_utc") and len(document["records"]) == 192,
            "Use a closed full 192-row result registry, never an active partial result")
    require(len(corpus["tasks"]) == 48 and len({t["root_id"] for t in corpus["tasks"]}) == 24,
            "Expected the frozen 48-task/24-root development corpus")
    audit = audit_document(document["records"], corpus["tasks"])
    audit.update({"checker_sha256": sha(Path(__file__).read_bytes()),
        "reference_checker_source_sha256": FROZEN_TASKS_SOURCE_SHA256,
        "input_sha256": {"records": sha(record_bytes), "tasks": sha(task_bytes)}})
    payload = json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not args.output.exists() or args.output.read_bytes() == payload, "Refusing to overwrite a different audit")
    args.output.write_bytes(payload)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        report = render_report(audit, args.output.as_posix())
        require(not args.report.exists() or args.report.read_text(encoding="utf-8") == report, "Refusing to overwrite a different report")
        args.report.write_text(report, encoding="utf-8")
    print(json.dumps({key: audit[key] for key in ("version", "reference_certificates_checked", "answer_diagnostics_checked",
        "recorded_primary_errors", "all_checked_recorded_labels_agree", "mismatch_trace_ids", "checker_sha256", "network_calls")}))


if __name__ == "__main__":
    main()
