"""Export complete reporting tables from fixed local analysis JSON, without fitting.

This reads the five saved analyses only. It never changes an estimand, selects
an outcome, calls an API or alters collection state.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ANALYSES = ("lexical", "bge", "qwen", "bge-matched", "qwen-matched")
LABELS = {"deepseek/deepseek-v4.1-flash": "DeepSeek", "openai/gpt-oss-20b": "GPT-OSS"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def gain_columns(gain):
    result = {key: gain.get(key) for key in ("status", "trace_count", "root_count", "interval_status",
                                            "log_loss_gain", "brier_gain")}
    for metric in ("log_loss_gain", "brier_gain"):
        interval = gain.get(metric + "_ci95")
        result[metric + "_ci95_low"] = interval[0] if interval is not None else None
        result[metric + "_ci95_high"] = interval[1] if interval is not None else None
    return result


def interval_text(gain, metric="log_loss_gain"):
    if gain.get("status") != "estimated":
        return "not estimated"
    point = gain[metric]
    interval = gain.get(metric + "_ci95")
    return f"{point:.5f} [{interval[0]:.5f}, {interval[1]:.5f}]" if interval is not None else f"{point:.5f} [not estimated]"


def build(input_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    documents, sources = {}, []
    for name in ANALYSES:
        path = input_dir / ("analysis-" + name + ".json")
        documents[name] = json.loads(path.read_text(encoding="utf-8"))
        sources.append({"path": path.as_posix(), "sha256": sha(path)})
    observed, metrics, controls = [], [], []
    secondary = ["# Observed probability score contrasts", "",
        "All saved observed-order contrasts are retained. Gains are static-minus-dynamic loss, equally weighted by original test root. Intervals are conditional pointwise 95% root-bootstrap intervals, without multiplicity correction. Raw error counts are not independent task counts. Constant fallback produces algebraic zero differences and does not establish equivalence.", "",
        "| Representation | Words | Target | Test traces / roots | Target errors | Log-loss gain [95% interval] | Brier gain [95% interval] | Dynamic fit |",
        "|---|---:|---|---:|---:|---|---|---|"]
    for name, document in documents.items():
        for run in document["runs"]:
            for fold in run["folds"]:
                target = fold["target_model"]
                identity = {"analysis": name, "population": document["analysis_population"],
                            "embedding_model": document["embedding_model"], "budget_words": run["budget_words"],
                            "order": run["order"], "order_seed": run["order_seed"], "target_model": target}
                if fold["status"] != "evaluated":
                    metrics.append({**identity, "fold_status": fold["status"], "reason": fold.get("reason")})
                    continue
                labels = [row["correct"] for row in fold["predictions"] if row["method"] == "dynamic"]
                errors = sum(label is False for label in labels)
                for method, fitted in fold["methods"].items():
                    metrics.append({**identity, "fold_status": "evaluated", "method": method,
                                    "estimator": fitted["estimator"], "C": fitted["C"],
                                    "source_validation_log_loss": fitted["source_validation_log_loss"],
                                    "target_raw_correct": sum(label is True for label in labels),
                                    "target_raw_errors": errors, **fitted["test"]})
                if run["order"] != "observed":
                    continue
                gain = run["paired_gain_by_target"][target]
                observed.append({**identity, "target_raw_errors": errors,
                                 "static_estimator": fold["methods"]["static"]["estimator"],
                                 "dynamic_estimator": fold["methods"]["dynamic"]["estimator"],
                                 "static_log_loss": fold["methods"]["static"]["test"]["log_loss"],
                                 "dynamic_log_loss": fold["methods"]["dynamic"]["test"]["log_loss"],
                                 "static_auroc": fold["methods"]["static"]["test"]["auroc"],
                                 "dynamic_auroc": fold["methods"]["dynamic"]["test"]["auroc"],
                                 **gain_columns(gain)})
                if "matched" not in name:
                    estimator = "constant fallback" if fold["methods"]["dynamic"]["estimator"].startswith("smoothed_constant") else "logistic"
                    secondary.append(f"| {name.upper()} | {run['budget_words']} | {LABELS.get(target, target)} | "
                        f"{gain.get('trace_count')} / {gain.get('root_count')} | {errors} | {interval_text(gain)} | "
                        f"{interval_text(gain, 'brier_gain')} | {estimator} |")
        for contrast in document["order_contrasts"]:
            for target, gain in contrast["paired_gain_by_target"].items():
                controls.append({"analysis": name, "population": document["analysis_population"],
                    "embedding_model": document["embedding_model"], "budget_words": contrast["budget_words"],
                    "control_order": contrast["control_order"], "control_seed": contrast["control_seed"],
                    "target_model": target, "estimand": contrast["estimand"],
                    "multiplicity": contrast["multiplicity"], **gain_columns(gain)})
    write_csv(output_dir / "observed-contrasts.csv", observed)
    write_csv(output_dir / "all-method-metrics.csv", metrics)
    write_csv(output_dir / "all-order-contrasts.csv", controls)
    (output_dir / "observed-secondary.md").write_text("\n".join(secondary) + "\n", encoding="utf-8", newline="\n")
    matching = {}
    for name in ("bge", "qwen"):
        original, matched = documents[name], documents[name + "-matched"]
        pairs = zip(original["runs"], matched["runs"])
        checks = []
        for first, second in pairs:
            checks.append({"budget_words": first["budget_words"], "order": first["order"],
                "order_seed": first["order_seed"],
                "predictions_and_fits_identical": first["folds"] == second["folds"],
                "target_gains_identical": first["paired_gain_by_target"] == second["paired_gain_by_target"],
                "matched_coverage": second.get("matched_embedding_coverage")})
        matching[name] = {"original_runs": len(original["runs"]), "matched_runs": len(matched["runs"]),
                          "all_prediction_fit_gain_checks_identical": len(original["runs"]) == len(matched["runs"])
                            and all(row["predictions_and_fits_identical"] and row["target_gains_identical"] for row in checks),
                          "checks": checks}
    (output_dir / "matched-embedding-check.json").write_text(json.dumps(matching, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    outputs = ["observed-contrasts.csv", "all-method-metrics.csv", "all-order-contrasts.csv",
               "observed-secondary.md", "matched-embedding-check.json"]
    manifest = {"schema_version": 1, "purpose": "deterministic_reporting_only_no_refit_or_new_inference",
                "script_sha256": sha(Path(__file__)), "sources": sources,
                "row_counts": {"observed_contrasts": len(observed), "all_method_metrics": len(metrics),
                               "all_order_contrasts": len(controls)},
                "outputs": [{"path": name, "sha256": sha(output_dir / name)} for name in outputs]}
    (output_dir / "manuscript-tables-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest["row_counts"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("artifacts/resumption-2026-11-08/local"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/resumption-2026-11-08/local/tables"))
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output), indent=2))


if __name__ == "__main__":
    main()
