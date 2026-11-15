"""Keyless descriptive analysis; reference is a machine instrument, not truth."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import random

from machine_development.annotation import ROLES


def bootstrap_draws(rows, replicates=2000, seed=20261115):
    """Replacement resampling of COMPLETE original root blocks, including missing labels."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["root_id"]].append(row)
    roots, rng = sorted(groups), random.Random(seed)
    return [[row for _ in roots for row in groups[rng.choice(roots)]] for __ in range(replicates)]


def pair_metrics(rows, left="reference_role", right="new_role"):
    pairs = [(row.get(left), row.get(right)) for row in rows
             if row.get(left) in ROLES and row.get(right) in ROLES]
    n, total = len(pairs), len(rows)
    matches = sum(a == b for a, b in pairs)
    a, b = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    matrix = Counter(pairs)
    raw = matches / n if n else None
    expected = sum(a[r] * b[r] for r in ROLES) / n ** 2 if n else None
    baseline_role = sorted(ROLES, key=lambda r: (-a[r], ROLES.index(r)))[0] if n else None
    return {"planned_items": total, "valid_pairs": n, "matches": matches,
            "invalid_or_unresolved": total - n,
            "reference_unresolved": sum(row.get(left) not in ROLES for row in rows),
            "new_invalid_or_missing": sum(row.get(right) not in ROLES for row in rows),
            "raw_agreement": raw, "cohen_kappa": (raw - expected) / (1 - expected) if expected is not None and expected < 1 else None,
            "agreement_over_planned": matches / total if total else None,
            "kappa_degenerate": expected == 1 if expected is not None else None,
            "majority_reference_role": baseline_role,
            "majority_label_baseline": max(a.values()) / n if n else None,
            "majority_baseline_scope": "descriptive in-sample reference majority on valid pairs; no trained model or accuracy",
            "confusion_matrix": {r: {c: matrix[r, c] for c in ROLES} for r in ROLES},
            "roles": {r: {"reference_n": a[r], "new_n": b[r], "matches": matrix[r, r],
                            "agreement_given_reference": matrix[r, r] / a[r] if a[r] else None}
                      for r in ROLES}}


def interval(values):
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    return {"interval95": [values[int(.025 * (len(values) - 1))], values[int(.975 * (len(values) - 1))]] if values else None,
            "defined_replicates": len(values)}


def comparison(rows, left="reference_role", right="new_role", replicates=2000):
    result = pair_metrics(rows, left, right)
    draws = bootstrap_draws(rows, replicates)
    metrics = [pair_metrics(draw, left, right) for draw in draws]
    keys = ("raw_agreement", "cohen_kappa", "agreement_over_planned", "majority_label_baseline")
    result["root_bootstrap"] = {"unit": "original_task_root", "roots": len({r["root_id"] for r in rows}),
        "replicates": replicates, "seed": 20261115,
        "metrics": {k: interval([m[k] for m in metrics]) for k in keys},
        "role_agreement": {role: interval([m["roles"][role]["agreement_given_reference"] for m in metrics]) for role in ROLES}}
    strata = {}
    for field in ("source_model", "domain", "length_bin", "context_bin", "has_context", "deepseek_round1_unanimous", "reference_status"):
        groups = defaultdict(list)
        for row in rows:
            groups[str(row.get(field))].append(row)
        strata[field] = {v: pair_metrics(group, left, right) for v, group in sorted(groups.items())}
    result["strata"] = strata
    return result


def paired_ablation(rows, replicates=2000):
    result = comparison(rows, "full_role", "ablated_role", replicates)
    valid = [r for r in rows if r.get("full_role") in ROLES and r.get("ablated_role") in ROLES]
    matched = [r for r in valid if r.get("reference_role") in ROLES]
    def delta(sample):
        eligible = [r for r in sample if all(r.get(k) in ROLES for k in ("reference_role", "full_role", "ablated_role"))]
        return sum((r["full_role"] == r["reference_role"]) - (r["ablated_role"] == r["reference_role"]) for r in eligible) / len(eligible) if eligible else None
    result.update(changed_labels=sum(r["full_role"] != r["ablated_role"] for r in valid), paired_valid=len(valid),
        paired_reference_valid=len(matched), full_minus_ablated_reference_agreement=delta(rows),
        delta_root_bootstrap=interval([delta(d) for d in bootstrap_draws(rows, replicates)]),
        interpretation="Paired context intervention plus uncontrolled single-call sampling variation; no accuracy claim")
    return result
