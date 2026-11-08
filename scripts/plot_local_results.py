"""Render scientific figures directly from the local summary and saved results.

No model calls, response rewriting, or manual data-coordinate adjustments.
PDF authoring requires the PDF operation marker in the invoking workflow.
Use --no-pdf for a temporary PNG-only implementation check.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


VERSION = "local-result-figures-v1"
COLORS = ("#4C78A8", "#F2A541", "#4F9D69", "#8D6BA8")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_name(model):
    return model.rsplit("/", 1)[-1]


def finite(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Figure values must be finite numbers or explicit nulls")
    return float(value)


def plot_data(summary, results):
    models = sorted(summary["planned_models"])
    aggregates = {model: Counter() for model in models}
    for row in summary["collection"]["by_model_domain_split"]:
        if row["model"] not in aggregates:
            raise ValueError("Coverage table includes an unplanned model")
        for field in ("planned", "trace_records", "reserved_without_trace", "dispatch_unknown",
                      "generation_completed", "gradeable", "gradeable_prefix_128",
                      "gradeable_prefix_256", "gradeable_prefix_512"):
            value = row.get(field, 0)
            if type(value) is not int or value < 0:
                raise ValueError("Coverage counts must be nonnegative integers")
            aggregates[row["model"]][field] += value
    eligible_results = {model: Counter() for model in models}
    traces = set()
    for record in results.get("records", []):
        if record["trace_id"] in traces:
            raise ValueError("Duplicate trace in the results input")
        traces.add(record["trace_id"])
        if record["model"] not in eligible_results:
            raise ValueError("Results include an unplanned model")
        if (record.get("status") != "completed" or record.get("gradable", True) is not True or
                type(record.get("correct")) is not bool):
            continue
        words = len(re.findall(r"\S+", record.get("text", "")))
        for budget in (128, 256, 512):
            eligible_results[record["model"]][str(budget)] += words >= budget
    # The summary can additionally recover saved trace.json records from the
    # complete journal. A smaller summary count signals inconsistent inputs.
    for model in models:
        for budget in (128, 256, 512):
            if aggregates[model][f"gradeable_prefix_{budget}"] < eligible_results[model][str(budget)]:
                raise ValueError("Summary prefix counts are smaller than the supplied results")
    candidates = [item for item in summary.get("analyses", []) if item.get("is_primary_BGE256_report")]
    if len(candidates) > 1:
        raise ValueError("Multiple original-population BGE analyses supplied; choose the intended input explicitly")
    primary = candidates[0] if candidates else None
    targets = {row["target_model"]: row for row in primary.get("targets_256", [])} if primary else {}
    transfer = [{"label": model_name(model), "model": model, "gain": targets.get(model, {}).get("gain"),
                 "status": targets.get(model, {}).get("status", "not_evaluated")}
                for model in models]
    controls = []
    if primary:
        order = sorted(primary.get("order_contrasts_256", []),
                       key=lambda row: (row["control_order"] != "reverse", row["control_order"], row["control_seed"]))
        for contrast in order:
            name = "reverse" if contrast["control_order"] == "reverse" else f"shuffle {contrast['control_seed']}"
            for model in models:
                controls.append({"label": f"{model_name(model)} / {name}", "model": model,
                                 "control_order": contrast["control_order"], "control_seed": contrast["control_seed"],
                                 "gain": contrast.get("paired_gain_by_target", {}).get(model)})
    routes = summary.get("admission", {}).get("routes", [])
    admitted = {route["model"] for route in routes if route.get("observed_trace_admitted") is True}
    admission_rows = summary.get("admission", {}).get("matrix", [])
    no_admission = [model for model in models if model not in admitted and
                    aggregates[model]["trace_records"] == 0 and any(
                        row["model"] == model and row["dispatch_status"] == "trace_record_saved" for row in admission_rows)]
    return {"models": models, "coverage": {model: dict(aggregates[model]) for model in models},
            "prefix_eligibility_from_results_only": {model: dict(eligible_results[model]) for model in models},
            "models_with_no_operational_admission_and_no_main_traces": no_admission,
            "transfer_BGE256": transfer, "order_controls_BGE256": controls,
            "primary_analysis_input": primary.get("input") if primary else None,
            "interpretation": "Exploratory observable-text results. E0 remains unpassed. Prefix eligibility conditions on completed, gradeable traces."}


def bars(data, fields, labels, title, ylabel, caption):
    figure, ax = plt.subplots(figsize=(8.4, 4.5), layout="constrained")
    positions = np.arange(len(data["models"]))
    width = .76 / len(fields)
    for index, (field, label) in enumerate(zip(fields, labels)):
        values = [data["coverage"][model].get(field, 0) for model in data["models"]]
        artists = ax.bar(positions + (index - (len(fields) - 1) / 2) * width, values,
                         width=width, label=label, color=COLORS[index])
        ax.bar_label(artists, fontsize=7.5, padding=3)
    ax.set_xticks(positions, [textwrap.fill(model_name(model), 22) for model in data["models"]])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12, loc="left", pad=12)
    ax.set_ylim(bottom=0)
    ax.margins(y=.18)
    ax.grid(axis="y", alpha=.18)
    ax.set_axisbelow(True)
    figure.legend(frameon=False, ncols=2, fontsize=8, loc="outside upper right")
    figure.supxlabel(caption, fontsize=8, wrap=True)
    return figure


def forest(rows, title, xlabel, caption):
    figure, ax = plt.subplots(figsize=(8.4, max(3.3, .40 * len(rows) + 1.8)), layout="constrained")
    if not rows or not any(finite((row.get("gain") or {}).get("log_loss_gain")) is not None for row in rows):
        ax.set_axis_off()
        ax.set_title(title, fontsize=12, loc="left", pad=12)
        message = "Not estimated\nNo eligible model-specific contrast is available."
        if rows:
            message += "\n\n" + "\n".join(f"{row['label']}: not estimated" for row in rows)
        ax.text(.5, .5, message, transform=ax.transAxes, ha="center", va="center", fontsize=10)
        figure.supxlabel(caption, fontsize=8, wrap=True)
        return figure
    labels = []
    for index, row in enumerate(rows):
        gain = row.get("gain") or {}
        point = finite(gain.get("log_loss_gain"))
        roots = gain.get("root_count")
        labels.append(row["label"] + (f" (roots={roots})" if roots is not None else ""))
        interval = gain.get("log_loss_gain_ci95")
        if point is None:
            ax.text(.02, index, "Not estimated", transform=ax.get_yaxis_transform(),
                    va="center", fontsize=8, color="#626970")
            continue
        if interval is None:
            ax.scatter([point], [index], facecolors="white", edgecolors=COLORS[0], marker="D", s=35, zorder=3)
            ax.annotate("CI not estimated", (point, index), xytext=(8, 0), textcoords="offset points",
                        fontsize=7.5, va="center", color="#626970")
        else:
            if not isinstance(interval, list) or len(interval) != 2:
                raise ValueError("A confidence interval must have two endpoints or be null")
            lower, upper = map(finite, interval)
            if lower is None or upper is None or lower > upper:
                raise ValueError("Malformed confidence interval")
            ax.hlines(index, lower, upper, color=COLORS[0], linewidth=1.7)
            ax.scatter([point], [index], color=COLORS[0], s=25, zorder=3)
    ax.axvline(0, color="#626970", linewidth=.8, linestyle="--")
    ax.set_yticks(range(len(rows)), labels, fontsize=8)
    # Missing-effect text does not expand data limits. Set the row extent
    # explicitly so an unavailable final model cannot disappear from the plot.
    ax.set_ylim(len(rows) - .5, -.5)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_title(title, fontsize=12, loc="left", pad=12)
    ax.margins(x=.25, y=.12)
    ax.grid(axis="x", alpha=.18)
    ax.set_axisbelow(True)
    figure.supxlabel(caption, fontsize=8, wrap=True)
    return figure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--outputdir", type=Path, required=True)
    parser.add_argument("--no-pdf", action="store_true", help="PNG-only temporary implementation check")
    args = parser.parse_args()
    summary, results = read(args.summary), read(args.results)
    input_hashes = {item["sha256"] for item in summary.get("inputs", [])}
    if input_hashes and sha(args.results) not in input_hashes:
        raise ValueError("Results bytes are not bound by the supplied summary")
    data = plot_data(summary, results)
    # This aggregate is separately named so a reservation is never relabeled as
    # a confirmed dispatch merely to complete a coverage bar.
    for row in data["coverage"].values():
        row["dispatched_or_reserved"] = row.get("trace_records", 0) + row.get("reserved_without_trace", 0)
    caption = "All planned task/model/sample rows. Completion refers to the exposed generation, before prefix eligibility."
    if data["models_with_no_operational_admission_and_no_main_traces"]:
        names = ", ".join(model_name(model) for model in data["models_with_no_operational_admission_and_no_main_traces"])
        caption += f"\nNo operational admission recorded; zero main-study traces: {names}."
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "pdf.fonttype": 42,
                         "ps.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.unicode_minus": False, "savefig.facecolor": "white"})
    figures = [
        ("01-collection-coverage", bars(data,
             ("planned", "dispatched_or_reserved", "generation_completed", "gradeable"),
             ("Planned", "Dispatched or reserved", "Completed generation", "Gradeable answer"),
             "Planned and observed collection coverage", "Attempt rows (count)", caption)),
        ("02-prefix-eligibility", bars(data,
             ("gradeable_prefix_128", "gradeable_prefix_256", "gradeable_prefix_512"),
             ("128 words", "256 words", "512 words"), "Coverage of fixed observable prefixes", "Eligible traces (count)",
             "Completed and gradeable traces; all train, validation and test rows.\nWhitespace words, not native model tokens; short traces are excluded, without padding.")),
        ("03-bge256-transfer", forest(data["transfer_BGE256"], "Added predictive value at 256 words\nBGE-M3; held-out models",
             "Static log loss - dynamic log loss\nPositive favors dynamics",
             "Exploratory pointwise 95% root-bootstrap intervals, conditional on fitted predictors.\nOpen diamonds mark point estimates whose intervals could not be estimated. E0 remains unpassed.")),
        ("04-bge256-order-controls", forest(data["order_controls_BGE256"], "Observed order versus refitted order controls\nBGE-M3; 256 words; separate target models",
             "Control dynamic log loss - observed-order dynamic log loss\nPositive favors observed order",
             "Direct paired contrasts on the same held-out roots. Separate exploratory pointwise intervals; no multiplicity adjustment.\nOpen diamonds mark point estimates with unavailable intervals.")),
    ]
    args.outputdir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for stem, figure in figures:
        png = args.outputdir / (stem + ".png")
        figure.savefig(png, dpi=300, metadata={"Software": VERSION})
        outputs.append({"path": png.name, "sha256": sha(png), "dpi": 300})
        if not args.no_pdf:
            pdf = args.outputdir / (stem + ".pdf")
            figure.savefig(pdf, metadata={"Creator": VERSION, "CreationDate": None, "ModDate": None})
            outputs.append({"path": pdf.name, "sha256": sha(pdf), "vector": True})
        plt.close(figure)
    (args.outputdir / "plot-data.json").write_bytes(encoded(data) + b"\n")
    manifest = {"plot_version": VERSION, "matplotlib_version": matplotlib.__version__,
                "summary_sha256": sha(args.summary), "results_sha256": sha(args.results),
                "coordinate_source": "saved summary and results; no manual data-coordinate adjustments",
                "outputs": outputs}
    (args.outputdir / "figures-manifest.json").write_bytes(encoded(manifest) + b"\n")
    print(json.dumps({"outputdir": str(args.outputdir), "figures": len(figures), "pdf_created": not args.no_pdf}))


if __name__ == "__main__":
    main()
