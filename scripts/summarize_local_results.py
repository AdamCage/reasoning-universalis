"""Build deterministic denominators and reporting tables without model calls.

Run from the repository root. A complete --calls snapshot distinguishes absent
dispatch from reserved attempts that never produced a trace record. Without
that snapshot, absent records are explicitly dispatch-unknown, not unsent.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import zipfile


VERSION = "local-result-summary-v1"
HISTORICAL_MEMBER = "evidence/stage0-budget.json"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def file_evidence(path):
    path = Path(path)
    resolved = path.resolve()
    label = str(resolved.relative_to(Path.cwd().resolve())).replace("\\", "/") \
        if resolved.is_relative_to(Path.cwd().resolve()) else path.name
    return {"path": label, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def key(record):
    if type(record.get("sample_index")) is not int:
        raise ValueError("Attempt needs an integer sample_index")
    return record["task_id"], record["model"], record["sample_index"]


def normalized_split(value):
    return {"validation": "val"}.get(value, value)


def attempt_inputs(document, calls=None, kind="generation"):
    records = list(document.get("records", []))
    journal = {}
    if calls is not None:
        calls = Path(calls)
        if not calls.is_dir():
            raise ValueError("--calls must name the complete existing calls directory")
        for path in sorted(calls.glob("*/reservation.json")):
            reservation = read(path)
            if reservation.get("kind") != kind:
                continue
            identity = reservation.get("identity", [])
            if not isinstance(identity, list) or len(identity) != 2 or type(identity[1]) is not int:
                raise ValueError("Unexpected journal generation identity")
            logical = identity[0], reservation["model"], identity[1]
            if logical in journal:
                raise ValueError("Repeated logical attempt in the calls journal")
            journal[logical] = {"call_id": reservation["call_id"],
                                "response_saved": (path.parent / "response.json").exists(),
                                "reservation_id": reservation.get("reservation_id")}
            trace = path.parent / "trace.json"
            if trace.exists():
                records.append(read(trace))
    by_key, trace_ids = {}, {}
    identity_fields = ("trace_id", "root_id", "task_id", "model", "sample_index", "status",
                       "observed_generation_status", "observed_trace_status", "correct", "text")
    for record in records:
        logical = key(record)
        if logical in by_key:
            if any(record.get(field) != by_key[logical].get(field) for field in identity_fields):
                raise ValueError("Conflicting records for the same planned attempt")
            continue
        trace_id = record["trace_id"]
        if trace_id in trace_ids and trace_ids[trace_id] != logical:
            raise ValueError("One trace ID occurs in different planned attempts")
        trace_ids[trace_id] = logical
        by_key[logical] = record
    if calls is not None:
        if by_key.keys() - journal.keys():
            raise ValueError("Complete calls journal is missing a recorded attempt reservation")
        if any(record["trace_id"] != journal[logical]["call_id"] for logical, record in by_key.items()):
            raise ValueError("Trace ID disagrees with its journal reservation")
    return by_key, journal


def planned_matrix(tasks, models, samples, document, calls=None, *, admission=False):
    if not tasks or len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("Tasks must be nonempty with unique task IDs")
    if len(set(models)) != len(models) or samples < 1:
        raise ValueError("Models must be unique and samples positive")
    root_partition = {}
    for task in tasks:
        partition = task["domain"], normalized_split(task["split"])
        if task["root_id"] in root_partition and root_partition[task["root_id"]] != partition:
            raise ValueError("A planned root crosses domain or split boundaries")
        root_partition[task["root_id"]] = partition
    records, journal = attempt_inputs(document, calls, "admission" if admission else "generation")
    sample_indices = (-1,) if admission else tuple(range(samples))
    planned = {(task["task_id"], model, sample) for task in tasks
               for model in models for sample in sample_indices}
    if records.keys() - planned or journal.keys() - planned:
        raise ValueError("Observed/journal attempts are outside the specified planned matrix")
    matrix = []
    for task in sorted(tasks, key=lambda row: row["task_id"]):
        for model in sorted(models):
            for sample in sample_indices:
                logical = task["task_id"], model, sample
                record, reservation = records.get(logical), journal.get(logical)
                row = {field: task.get(field) for field in ("task_id", "root_id", "domain", "family", "difficulty")}
                row.update(model=model, sample_index=sample, split=normalized_split(task["split"]))
                if record:
                    if (record["root_id"] != task["root_id"] or record.get("domain") != task["domain"] or
                            (not admission and normalized_split(record["split"]) != row["split"])):
                        raise ValueError("Attempt task metadata disagrees with the bound corpus")
                    gradeable = type(record.get("correct")) is bool and record.get("gradable", True) is True
                    generation = record.get("observed_generation_status", record.get("status"))
                    predictor = record.get("status") == "completed"
                    text = record.get("text", "")
                    row.update(dispatch_status="trace_record_saved", trace_id=record["trace_id"],
                               generation_completed=generation == "completed", predictor_completed=predictor,
                               gradeable=gradeable, correct=record.get("correct") if gradeable else None,
                               grading_verdict=record.get("grading", {}).get("verdict", "not_evaluated"),
                               finish_reason=record.get("finish_reason"),
                               observed_trace_status=record.get("observed_trace_status"),
                               truncated=record.get("finish_reason") == "length",
                               retained_words=len(re.findall(r"\S+", text)),
                               prefix_coverage={str(budget): predictor and gradeable and len(re.findall(r"\S+", text)) >= budget
                                                for budget in (128, 256, 512)})
                else:
                    dispatch = ("response_saved_without_trace_record" if reservation and reservation["response_saved"]
                                else "reserved_without_trace_record" if reservation
                                else "not_dispatched" if calls is not None
                                else "no_trace_record_dispatch_unknown")
                    row.update(dispatch_status=dispatch, trace_id=reservation["call_id"] if reservation else None,
                               generation_completed=False, predictor_completed=False, gradeable=False,
                               correct=None, grading_verdict="not_evaluated", finish_reason=None,
                               observed_trace_status=None, truncated=False, retained_words=None,
                               prefix_coverage={str(budget): False for budget in (128, 256, 512)})
                matrix.append(row)
    return matrix


def counts(rows):
    result = Counter(planned=len(rows), trace_records=0, not_dispatched=0, reserved_without_trace=0,
                     dispatch_unknown=0, generation_completed=0, predictor_completed=0,
                     gradeable=0, correct=0, incorrect=0, unparseable=0, truncated=0)
    for row in rows:
        result["trace_records"] += row["dispatch_status"] == "trace_record_saved"
        result["not_dispatched"] += row["dispatch_status"] == "not_dispatched"
        result["reserved_without_trace"] += row["dispatch_status"] in {
            "reserved_without_trace_record", "response_saved_without_trace_record"}
        result["dispatch_unknown"] += row["dispatch_status"] == "no_trace_record_dispatch_unknown"
        for field in ("generation_completed", "predictor_completed", "gradeable", "truncated"):
            result[field] += bool(row[field])
        result["correct"] += row["correct"] is True
        result["incorrect"] += row["correct"] is False
        result["unparseable"] += row["grading_verdict"] == "unparseable"
        for budget in (128, 256, 512):
            result[f"gradeable_prefix_{budget}"] += row["prefix_coverage"][str(budget)]
    return {**dict(result), "correct_fraction_of_gradeable": result["correct"] / result["gradeable"]
            if result["gradeable"] else None,
            "correct_fraction_of_planned": result["correct"] / result["planned"] if result["planned"] else None}


def coverage_tables(matrix):
    grouped = defaultdict(list)
    blocks = defaultdict(list)
    for row in matrix:
        grouped[(row["model"], row["domain"], row["split"])].append(row)
        blocks[(row["model"], row["domain"], row["split"], row["root_id"])].append(row)
    root_blocks = [{**dict(zip(("model", "domain", "split", "root_id"), group)),
                    **counts(rows), "generation_complete_block": all(row["generation_completed"] for row in rows),
                    "predictor_complete_block": all(row["predictor_completed"] for row in rows),
                    "gradeable_complete_block": all(row["gradeable"] for row in rows)}
                   for group, rows in sorted(blocks.items())]
    table = []
    for group, rows in sorted(grouped.items()):
        own_blocks = [block for block in root_blocks if tuple(block[field] for field in ("model", "domain", "split")) == group]
        table.append({**dict(zip(("model", "domain", "split"), group)), **counts(rows),
                      "planned_roots": len(own_blocks),
                      "generation_complete_roots": sum(block["generation_complete_block"] for block in own_blocks),
                      "predictor_complete_roots": sum(block["predictor_complete_block"] for block in own_blocks),
                      "gradeable_complete_roots": sum(block["gradeable_complete_block"] for block in own_blocks)})
    return table, root_blocks


def budget_summary(ledger, historical, cap):
    if ledger[:len(historical)] != historical:
        raise ValueError("Historical ledger prefix changed or disappeared")

    def subtotal(rows):
        known, unknown, excess, committed = Decimal(0), Decimal(0), Decimal(0), Decimal(0)
        states = Counter()
        for row in rows:
            amount = Decimal(str(row["charged_or_reserved_rub"]))
            if not amount.is_finite() or amount < 0:
                raise ValueError("Invalid budget commitment")
            committed += amount
            states[row["state"]] += 1
            if row.get("reported_cost_rub") is None:
                unknown += amount
            else:
                cost = Decimal(str(row["reported_cost_rub"]))
                if not cost.is_finite() or cost < 0 or amount < cost:
                    raise ValueError("Invalid reported cost or released obligation")
                known += cost
                excess += amount - cost
        return {"rows": len(rows), "states": dict(sorted(states.items())),
                "charged_or_reserved_rub": str(committed), "reported_cost_rub": str(known),
                "retained_reservation_above_reported_cost_rub": str(excess),
                "commitments_without_reported_cost_rub": str(unknown)}

    current = ledger[len(historical):]
    purposes = sorted({row["purpose"] for row in current})
    total = subtotal(ledger)
    return {"historical_prefix_preserved": True, "all": total,
            "historical": subtotal(historical), "new": subtotal(current),
            "new_by_purpose": {purpose: subtotal([row for row in current if row["purpose"] == purpose]) for purpose in purposes},
            "cap_rub": str(cap), "remaining_after_all_commitments_rub": str(cap - Decimal(total["charged_or_reserved_rub"])),
            "interpretation": "Reported costs are observed charges; commitments also retain conservative and unknown reserves. Missing cost is not zero."}


def analysis_tables(paths):
    outputs = []
    for path in sorted(paths, key=str):
        document = read(path)
        runs = [run for run in document.get("runs", []) if run.get("budget_words") == 256 and run.get("order") == "observed"]
        targets = [{"target_model": fold["target_model"], "status": fold["status"],
                    "counts": fold.get("counts"), "test_roots": fold.get("test_roots"),
                    "class_balance": fold.get("methods", {}).get("static", {}).get("test", {}).get("correct_rate"),
                    "static_test": fold.get("methods", {}).get("static", {}).get("test"),
                    "dynamic_test": fold.get("methods", {}).get("dynamic", {}).get("test"),
                    "gain": run.get("paired_gain_by_target", {}).get(fold["target_model"])}
                   for run in runs for fold in run.get("folds", [])]
        outputs.append({"input": file_evidence(path), "embedding_model": document.get("embedding_model"),
                        "analysis_population": document.get("analysis_population", "original_embedder_specific_eligible_prefixes"),
                        "scientific_status": document.get("scientific_status"), "E0": document.get("E0"),
                        "is_primary_BGE256_report": document.get("embedding_model") == "baai/bge-m3" and
                            document.get("matched_embedding_model") is None,
                        "targets_256": targets,
                        "order_contrasts_256": [contrast for contrast in document.get("order_contrasts", [])
                                                if contrast.get("budget_words") == 256]})
    return outputs


def markdown(summary):
    overall = summary["collection"]["overall"]
    lines = ["# Local collection results", "", "Exploratory observable-text pilot. E0 remains unpassed.", "",
             f"Planned rows: {overall['planned']}; saved traces: {overall['trace_records']}; "
             f"gradeable answers: {overall['gradeable']}; correct: {overall['correct']}.", "",
             "Counts of unparseable output and truncation overlap other status counts.", "",
             "| Model | Domain | Split | Planned | Saved | Unsent | Reserved without trace | Gradeable | Correct | Truncated | Complete roots |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in summary["collection"]["by_model_domain_split"]:
        lines.append("| " + " | ".join(str(row[field]) for field in
                     ("model", "domain", "split", "planned", "trace_records", "not_dispatched",
                      "reserved_without_trace", "gradeable", "correct", "truncated", "generation_complete_roots")) + " |")
    lines += ["", "## Primary BGE result at 256 words", "",
              "Positive static-minus-dynamic log loss favors the dynamic predictor. Intervals are exploratory and conditional on fitted predictors.", ""]
    primary = [item for item in summary["analyses"] if item["is_primary_BGE256_report"]]
    if not primary:
        lines.append("Not evaluated: no original-population BGE analysis was supplied.")
    for item in primary:
        lines += [f"Input: {item['input']['path']}", "",
                  "| Target | Status | Roots | Traces | Correct fraction | Log loss gain | 95% interval |",
                  "|---|---|---:|---:|---:|---:|---|"]
        for target in item["targets_256"]:
            gain = target.get("gain") or {}
            lines.append("| " + " | ".join(str(value) for value in (target["target_model"], target["status"],
                         gain.get("root_count"), gain.get("trace_count"), target["class_balance"],
                         gain.get("log_loss_gain"), gain.get("log_loss_gain_ci95"))) + " |")
        if not item["targets_256"]:
            lines.append("No 256-word observed-order contrast was available.")
        lines += ["", "Direct refitted order contrasts are preserved, separately by target, in summary.json.", ""]
    if summary["budget"] is not None:
        budget = summary["budget"]
        lines += ["## Budget", "", f"Reported costs: {budget['all']['reported_cost_rub']} RUB. "
                  f"Charged or reserved: {budget['all']['charged_or_reserved_rub']} RUB. "
                  f"Remaining after commitments: {budget['remaining_after_all_commitments_rub']} RUB.", "",
                  budget["interpretation"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--calls", type=Path, help="Complete calls journal; required to establish not-dispatched rows")
    parser.add_argument("--admission", type=Path, action="append", default=[])
    parser.add_argument("--analysis", type=Path, action="append", default=[])
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--historical-archive", type=Path, default=Path("evidence/stage0-2026-10-12.zip"))
    parser.add_argument("--models", help="Override planned model identities explicitly, comma separated")
    parser.add_argument("--samples", type=int, help="Override planned samples per task explicitly")
    parser.add_argument("--output", type=Path, required=True, help="Directory for summary.json, planned-matrix.json and coverage.md")
    args = parser.parse_args()
    corpus, protocol, results = read(args.tasks), read(args.protocol), read(args.results)
    models = [model.strip() for model in args.models.split(",")] if args.models else protocol["models"]["candidates"]
    samples = args.samples if args.samples is not None else protocol["generation"]["samples_per_task"]
    tasks = corpus["tasks"] if isinstance(corpus, dict) else corpus
    matrix = planned_matrix(tasks, models, samples, results, args.calls)
    coverage, blocks = coverage_tables(matrix)
    admission_documents = [read(path) for path in args.admission]
    admission_results = [document for document in admission_documents if "records" in document]
    if len(admission_results) > 1:
        raise ValueError("Supply one admission-results document, plus optional routes documents")
    admission_matrix = []
    if isinstance(corpus, dict) and corpus.get("admission_tasks"):
        admission_matrix = planned_matrix(corpus["admission_tasks"], models, 1,
                                          admission_results[0] if admission_results else {"records": []},
                                          args.calls, admission=True)
    budget = None
    if args.ledger:
        with zipfile.ZipFile(args.historical_archive) as archive:
            historical = json.loads(archive.read(HISTORICAL_MEMBER))
        cap = Decimal(str(results.get("budget", {}).get("cap_rub", protocol["budget"]["cap_total_rub"])))
        budget = budget_summary(read(args.ledger), historical, cap)
    inputs = [args.results, args.tasks, args.protocol] + args.admission + args.analysis
    if args.ledger:
        inputs += [args.ledger, args.historical_archive]
    summary = {"summary_version": VERSION, "E0": "not_passed", "scientific_validity": "not_assessed",
               "planned_models": models, "samples_per_task": samples, "inputs": [file_evidence(path) for path in inputs],
               "dispatch_classification": "complete_calls_journal" if args.calls else "missing_records_dispatch_unknown",
               "collection": {"overall": counts(matrix), "by_model_domain_split": coverage, "root_blocks": blocks,
                              "reported_dispatch_failures": results.get("failures", [])},
               "admission": {"overall": counts(admission_matrix), "matrix": admission_matrix,
                             "routes": [route for document in admission_documents for route in document.get("routes", [])]},
               "analyses": analysis_tables(args.analysis), "budget": budget,
               "counting_notes": ["Every task/model/sample is retained in the planned denominator.",
                                  "Reserved attempts need not have reached the service; missing responses remain unresolved.",
                                  "Root block completion is based on all planned variants and samples, never selected by correctness.",
                                  "Unparseable, truncated and excluded counts can overlap."]}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_bytes(encoded(summary) + b"\n")
    (args.output / "planned-matrix.json").write_bytes(encoded(matrix) + b"\n")
    (args.output / "coverage.md").write_text(markdown(summary), encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "planned": len(matrix), "saved_traces": summary["collection"]["overall"]["trace_records"]}))


if __name__ == "__main__":
    main()
