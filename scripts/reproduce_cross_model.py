"""Rebuild cross-model tables and figures without a key or network access.

Before budget approval, this computes only the fixed sample and existing
DeepSeek controls; cross-family results remain explicitly unavailable.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cross_model.analysis import comparison, pair_metrics, bootstrap_draws, interval, paired_ablation
from cross_model.common import ARTIFACT, ROUTES, PROTOCOL, read, sha, write
from cross_model.annotation import validate_envelope
from machine_development.annotation import ROLES


def loo_role(roles):
    other = roles[1:]
    if len(other) != 4 or any(r not in ROLES for r in other):
        return None
    counts = Counter(other)
    return next((r for r in ROLES if counts[r] >= 3), None)


def rows_from_mapping(mapping):
    rows = []
    for identity, m in mapping.items():
        n, c = m["segment_characters"], m["context_characters"]
        roles = m["deepseek_round1_roles"]
        rows.append({"item_id": identity, **m, "length_bin": "01:<=50" if n <= 50 else "02:51-150" if n <= 150 else "03:>150",
            "context_bin": "01:<=250" if c <= 250 else "02:251-750" if c <= 750 else "03:>750",
            "ds0": roles[0] if roles else None, "ds1": roles[1] if len(roles)>1 else None, "ds_loo4": loo_role(roles)})
    return rows


def verify(project, base):
    for path, digest in read(base / "parent-integrity.json")["files"].items():
        if sha((project / path).read_bytes()) != digest:
            raise ValueError("Original frozen evidence differs: " + path)
    protocol_path = project / PROTOCOL
    if protocol_path.exists():
        for path, digest in read(protocol_path)["frozen_files"].items():
            if sha((project / path).read_bytes()) != digest:
                raise ValueError("Frozen cross-model file differs: " + path)


def analyze(project=ROOT, output_dir=None, replicates=2000):
    project = Path(project)
    base = project / ARTIFACT
    output = Path(output_dir) if output_dir else base / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    verify(project, base)
    mapping = read(base / "mapping.json")["items"]
    rows = rows_from_mapping(mapping)
    result = {"status": "offline_existing_data_only", "new_paid_calls": 0,
        "scope": "Exploratory fixed development sample; machine instruments, no ground truth, E0 not passed",
        "bootstrap_unit": "original_task_root", "bootstrap_replicates": replicates,
        "sample_counts": {s: sum(r["sample"] == s for r in rows) for s in ("core", "challenge")},
        "same_model_controls": {}, "cross_family": {}, "cross_family_pair": {}, "context_ablation": {}, "paired_instrument_gap": {}}
    for sample in ("core", "challenge", "pooled"):
        selected = [r for r in rows if sample == "pooled" or r["sample"] == sample]
        result["same_model_controls"][sample] = {
            "ds0_vs_ds1": comparison(selected, "ds0", "ds1", replicates),
            "ds0_vs_loo4": comparison(selected, "ds_loo4", "ds0", replicates),
            "ds0_vs_final_consensus_circular": pair_metrics(selected, "reference_role", "ds0")}
    new_path = base / "new-annotations.json"
    annotations = read(new_path) if new_path.exists() else None
    if annotations:
        protocol_digest = sha((project / PROTOCOL).read_bytes())
        if annotations["protocol_sha256"] != protocol_digest:
            raise ValueError("New annotation protocol binding differs")
        cells = annotations["cells"]
        identities = [(c["model"], c["condition"], c["item_id"]) for c in cells]
        if len(identities) != len(set(identities)):
            raise ValueError("Repeated new annotation cell")
        from cross_model.runner import cells as expected_cells
        expected = {(c["model"], c["condition"], c["item_id"]): c for c in expected_cells(read(base / "input-items.json"), read(base / "codebook.json"))}
        if set(identities) != set(expected):
            raise ValueError("New annotation roster differs; no extra or omitted cells allowed")
        # Re-parse every available RAW response instead of trusting derived votes.
        for c in cells:
            if "call_id" not in c or c.get("technical_status") == "unknown":
                continue
            directory = project / ".research/resumption-2026-11-08-live/cross-model" / protocol_digest / "calls" / c["call_id"]
            # Portable exported raw files take precedence outside the live state.
            exported = base / "raw" / c["call_id"]
            if exported.is_dir():
                directory = exported
            response_path = directory / "response.json"
            request_path = directory / "request.json"
            if sha(response_path.read_bytes()) != c["response_sha256"] or sha(request_path.read_bytes()) != c["request_sha256"]:
                raise ValueError("Raw request/response hash differs")
            if read(request_path) != expected[c["model"], c["condition"], c["item_id"]]["request"]:
                raise ValueError("Raw request differs from the frozen prompt-safe condition")
            item = next((i for i in read(base / "input-items.json")["items"] if i["item_id"] == c["item_id"]), None)
            if item is None:
                from cross_model.annotation import probe_item
                item = probe_item()
            parsed = validate_envelope(read(response_path), item, c["model"], c["provider"])
            if any(c.get(k) != parsed[k] for k in ("vote", "technical_status", "invalid_reason", "returned_reasoning_present")):
                raise ValueError("Derived vote differs from strict raw replay")
        lookup = {(c["model"], c["condition"], c["item_id"]): c for c in cells}
        def role(model, condition, identity):
            cell = lookup.get((model, condition, identity), {})
            return cell.get("vote", {}).get("primary_role") if type(cell.get("vote")) is dict and cell.get("technical_status") == "valid" else None
        result.update(status="measured_cross_family_exploratory", new_paid_calls=sum("call_id" in c and c.get("technical_status") != "not_dispatched" for c in cells),
            technical_status_counts=dict(Counter(c["technical_status"] for c in cells)),
            annotation_sha256=sha(new_path.read_bytes()))
        for model, _ in ROUTES:
            key = model.replace("/", "_")
            for row in rows:
                row[key] = role(model, "full_context", row["item_id"])
                row[key + ":ablated"] = role(model, "without_context", row["item_id"])
            result["cross_family"][model] = {}
            result["paired_instrument_gap"][model] = {}
            for sample in ("core", "challenge", "pooled"):
                selected = [{**r, "new_role": r[key]} for r in rows if sample == "pooled" or r["sample"] == sample]
                result["cross_family"][model][sample] = comparison(selected, replicates=replicates)
                matched = [r for r in selected if all(r.get(k) in ROLES for k in ("ds_loo4", "ds0", "new_role"))]
                def gap(draw):
                    return sum((r["ds0"] == r["ds_loo4"]) - (r["new_role"] == r["ds_loo4"]) for r in draw) / len(draw) if draw else None
                result["paired_instrument_gap"][model][sample] = {"planned": len(selected), "matched_valid": len(matched),
                    "ds0_vs_loo4": pair_metrics(matched, "ds_loo4", "ds0"), "new_vs_loo4": pair_metrics(matched, "ds_loo4", "new_role"),
                    "same_minus_cross_agreement": gap(matched), "root_bootstrap": interval([gap(d) for d in bootstrap_draws(matched, replicates)]),
                    "note": "Held-out DeepSeek vote0 never contributes to four-vote reference; reference requires >=3/4. Same prompt, sampling and consensus asymmetries remain."}
            ablated = [{**r, "full_role": r[key], "ablated_role": r[key+":ablated"]} for r in rows if r["ablation"]]
            result["context_ablation"][model] = paired_ablation(ablated, replicates)
        for sample in ("core", "challenge", "pooled"):
            result["cross_family_pair"][sample] = comparison([r for r in rows if sample == "pooled" or r["sample"] == sample],
                ROUTES[0][0].replace("/", "_"), ROUTES[1][0].replace("/", "_"), replicates)
    write(output / "summary.json", result)
    write(output / "item-level.json", {"rows": rows})
    table = []
    for model, values in result["cross_family"].items():
        for sample, metrics in values.items():
            table.append({"model": model, "sample": sample, **{k: metrics[k] for k in ("planned_items", "valid_pairs", "matches", "raw_agreement", "cohen_kappa", "agreement_over_planned", "majority_label_baseline")}})
            matrix = metrics["confusion_matrix"]
            with (output / (model.replace("/", "_")+"-"+sample+"-confusion.csv")).open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f); writer.writerow(["DeepSeek_reference_role", *ROLES])
                writer.writerows([role, *[matrix[role][c] for c in ROLES]] for role in ROLES)
    if table:
        with (output / "agreement.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(table[0])); writer.writeheader(); writer.writerows(table)
    print({"status": result["status"], "new_paid_calls": result["new_paid_calls"], "output": str(output)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args()
    analyze(output_dir=args.output, replicates=args.bootstrap)


if __name__ == "__main__":
    main()
