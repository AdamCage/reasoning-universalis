"""Offline support checks and explicitly hypothetical planning for pilot v2.

This module does not fit a classifier, generate tasks, open a future test set,
call an API, or rewrite labels. Repeated/paired variants count once per root.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import NormalDist, mean, median


VERSION = "pilot-v2-statistical-design-v1"
PRIMARY_PREFIX_WORDS = 256
PREFIX_BUDGETS = (128, 256, 512)
OUTPUT_BUDGETS = (2048, 8192)
ROOT_FLOORS = {"probe": 3, "source_train": 10, "source_validation": 5, "target": 20}
MIN_GRADEABLE_COMPLETION = .75
CATEGORIES = ("none", "error_only", "correct_only", "mixed")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def wilson_interval(successes, trials, level=.95):
    """Binomial Wilson interval, only under the stated independent-root model."""
    require(type(trials) is int and type(successes) is int and 0 <= successes <= trials,
            "Wilson counts require integer 0 <= successes <= trials")
    require(0 < level < 1, "Confidence level must be between zero and one")
    if trials == 0:
        return None
    z = NormalDist().inv_cdf((1 + level) / 2)
    p = successes / trials
    divisor = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / divisor
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / divisor
    return [max(0., center - half), min(1., center + half)]


def binomial_probabilities(n, probability):
    require(type(n) is int and n >= 0 and 0 <= probability <= 1,
            "Binomial scenario needs nonnegative integer roots and probability in [0,1]")
    if probability in (0, 1):
        return [float(k == (n if probability == 1 else 0)) for k in range(n + 1)]
    logs = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(probability) + (n - k) * math.log1p(-probability) for k in range(n + 1)]
    largest = max(logs)
    values = [math.exp(value - largest) for value in logs]
    total = math.fsum(values)
    return [value / total for value in values]


def binomial_tail(n, probability, minimum):
    require(type(minimum) is int and minimum >= 0, "Minimum root count must be a nonnegative integer")
    return math.fsum(binomial_probabilities(n, probability)[minimum:]) if minimum <= n else 0.


def binomial_failure_probability(n, probability, minimum):
    """Pr[Bin(n,p) < minimum], computed in O(minimum), not O(n)."""
    require(type(n) is int and n >= 0 and 0 <= probability <= 1 and
            type(minimum) is int and minimum >= 1, "Invalid root-support binomial parameters")
    if n < minimum or probability == 0:
        return 1.
    if probability == 1:
        return 0.
    terms = [math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                      + k * math.log(probability) + (n - k) * math.log1p(-probability))
             for k in range(minimum)]
    return min(1., max(0., math.fsum(terms)))


def required_roots_for_support(error_probability, correct_probability, error_floor, correct_floor,
                               required_joint_probability=.90, maximum_roots=10000):
    """Smallest N passing a conservative joint-class union-bound criterion.

    Roots, not paired variants, are the Bernoulli trials. Error and correct
    indicators within a root need not be independent.
    """
    require(0 < required_joint_probability < 1 and type(maximum_roots) is int and maximum_roots >= 1,
            "Invalid prospective joint support probability or search cap")
    def bound(n):
        return max(0., 1 - binomial_failure_probability(n, error_probability, error_floor)
                   - binomial_failure_probability(n, correct_probability, correct_floor))
    if bound(maximum_roots) < required_joint_probability:
        return {"required_roots": None, "status": "infeasible_within_search_cap",
                "maximum_roots": maximum_roots, "joint_support_lower_bound_at_cap": bound(maximum_roots)}
    low, high = 0, maximum_roots
    while low + 1 < high:
        middle = (low + high) // 2
        if bound(middle) >= required_joint_probability:
            high = middle
        else:
            low = middle
    return {"required_roots": high, "status": "conditional_iid_root_candidate_not_registered_N",
            "maximum_roots": maximum_roots, "joint_support_lower_bound": bound(high),
            "previous_N_joint_lower_bound": bound(high - 1)}


def required_n_tables(scenarios):
    support = []
    for name, probabilities in scenarios.items():
        error = probabilities["error_only"] + probabilities["mixed"]
        correct = probabilities["correct_only"] + probabilities["mixed"]
        for role, floor in ROOT_FLOORS.items():
            support.append({"scenario": name, "role": role, "error_root_probability": error,
                "correct_root_probability": correct, "minimum_error_roots": floor, "minimum_correct_roots": floor,
                "required_joint_probability": .90,
                **required_roots_for_support(error, correct, floor, floor)})
    precision = [{"assumed_root_sd": sd, "target_CI_half_width": half,
                  "normal_critical_value": 1.96, "required_roots": math.ceil((1.96 * sd / half) ** 2),
                  "scope": "conditional_known_sigma_normal_precision_planning_not_validated_power"}
                 for sd in (.05, .10) for half in (.005, .01, .02)]
    return {"support": support, "precision": precision,
            "joint_rule": "1-Pr(Bin(N,p_error)<k_error)-Pr(Bin(N,p_correct)<k_correct)>=0.90",
            "assumptions": "independent identically distributed root indicators; paired variants are within-root, and within-root class independence is not required",
            "limitations": "hypothetical scenario probabilities and SDs; blocked heterogeneous strata require separate planning; no final N or corpus is selected"}


def output_budget(record, explicit_default=None):
    values = [record[name] for name in ("output_budget_tokens", "output_budget", "max_output_tokens") if name in record]
    if not values:
        require(explicit_default is not None, "Missing explicit output-budget condition")
        values = [explicit_default]
    require(all(type(value) is int and value > 0 for value in values) and len(set(values)) == 1,
            "Conflicting or invalid output-budget conditions")
    return values[0]


def prefix_text(record):
    import re
    text = record.get("text", "")
    require(isinstance(text, str), "Reasoning text must be a string")
    # Identical prospective censoring rule to v1; never recover text from answer.
    return text.split("ANSWER:", 1)[0], re.findall(r"\S+", text.split("ANSWER:", 1)[0])


def diagnostic_censored_label(record):
    labels = []
    for name in ("raw_answer_grading", "diagnostic_grading"):
        verdict = (record.get(name) or {}).get("verdict")
        if verdict in ("correct", "incorrect"):
            labels.append(verdict == "correct")
    require(len(set(labels)) <= 1, "Conflicting diagnostic censored-answer verdicts")
    return labels[0] if labels else None


def task_index(tasks):
    indexed, roots = {}, {}
    for task in tasks:
        identity, root = task["task_id"], task["root_id"]
        require(identity not in indexed, "Repeated planned task ID")
        tier = task.get("tier", task.get("difficulty"))
        require(isinstance(root, str) and root and isinstance(tier, str) and tier,
                "Each planned task needs root_id and tier/difficulty")
        metadata = task["domain"], tier
        require(root not in roots or roots[root] == metadata, "A root crosses domain/tier strata")
        indexed[identity], roots[root] = task, metadata
    require(bool(indexed), "Empty planned task set")
    return indexed, roots


def validate_probe_layout(tasks):
    indexed, roots = task_index(tasks)
    variants = Counter(task["root_id"] for task in indexed.values())
    strata = Counter(roots.values())
    require(len(roots) == 24 and len(indexed) == 48 and set(variants.values()) == {2},
            "Probe requires 24 roots and two planned variants per root")
    require(len({domain for domain, _ in roots.values()}) == 4 and
            len({tier for _, tier in roots.values()}) == 3 and len(strata) == 12 and set(strata.values()) == {2},
            "Probe requires four domains x three tiers x two roots")
    return {"roots": 24, "tasks": 48, "domains": 4, "tiers": 3,
            "variants_per_root": 2, "conditions_per_task": 4, "maximum_generation_calls": 192}


def summarize_support(records, tasks, models, output_budgets=OUTPUT_BUDGETS,
                      prefix_budgets=PREFIX_BUDGETS, stage="development_probe", explicit_default_output_budget=None):
    """Report planned denominators and roots with eligible observed labels.

    Primary policy is always finish-stop-only. Censored answers are diagnostic
    even if a separate final-answer parser can extract a label from them.
    """
    require(stage in ("development_probe", "calibration", "final_assessment", "historical_development"),
            "Unknown stage")
    require(len(set(models)) == len(models) and models and output_budgets and
            len(set(output_budgets)) == len(output_budgets) and all(type(value) is int and value > 0 for value in output_budgets),
            "Models and output budgets must be nonempty and unique")
    require(PRIMARY_PREFIX_WORDS in prefix_budgets and len(set(prefix_budgets)) == len(prefix_budgets)
            and all(type(b) is int and b > 0 for b in prefix_budgets),
            "Report primary 256 and valid prefix budgets")
    indexed, root_metadata = task_index(tasks)
    observed, traces = {}, set()
    for record in records:
        budget = output_budget(record, explicit_default_output_budget)
        task = indexed.get(record.get("task_id"))
        require(task is not None and record.get("model") in models and budget in output_budgets,
                "Record outside the declared planned task/model/budget matrix")
        require(record.get("root_id") == task["root_id"] and record.get("domain") == task["domain"],
                "Record/task root or domain mismatch")
        logical = record["task_id"], record["model"], budget
        require(isinstance(record.get("trace_id"), str) and record["trace_id"], "Missing trace ID")
        require(logical not in observed and record.get("trace_id") not in traces, "Repeated attempt or trace ID")
        require(record.get("correct") is None or type(record["correct"]) is bool, "Correctness must be Boolean or null")
        censored = record.get("budget_censored") is True or record.get("finish_reason") == "length"
        require(not censored or record.get("correct") is None,
                "Budget-censored primary correctness must remain null; use a diagnostic verdict separately")
        traces.add(record.get("trace_id"))
        observed[logical] = record
    groups = []
    for model in sorted(models):
        for output in sorted(output_budgets):
            for prefix in sorted(prefix_budgets):
                counters = Counter(planned_attempts=len(indexed), represented_cells=0, recorded_attempts=0,
                                   not_dispatched=0, unattempted_intents=0, unknown_attempts=0,
                                   completed_gradeable=0, eligible_traces=0, correct_traces=0, error_traces=0,
                                   censored_attempts=0, censored_diagnostic_gradeable=0,
                                   censored_diagnostic_prefix_eligible=0, operational_validation_excluded=0)
                flags = {root: {"correct": False, "error": False, "recorded": 0,
                                "diagnostic_correct": False, "diagnostic_error": False}
                         for root in root_metadata}
                for task_id, task in indexed.items():
                    record = observed.get((task_id, model, output))
                    if record is None:
                        continue
                    counters["represented_cells"] += 1
                    status = record.get("status")
                    if status == "not_dispatched":
                        counters["not_dispatched"] += 1
                        continue
                    unknown = (status in {"unknown", "unresolved", "unresolved_attempt", "unresolved_intent",
                                          "transport_failed", "transport_error"}
                               or record.get("request_state") == "unknown" or record.get("unknown") is True
                               or ("http_status" in record and record["http_status"] is None))
                    counters["unknown_attempts"] += unknown
                    attempted = record.get("attempted", status != "unresolved_intent") is True
                    if not attempted:
                        counters["unattempted_intents"] += status == "unresolved_intent"
                        continue
                    counters["recorded_attempts"] += 1
                    root = flags[task["root_id"]]
                    root["recorded"] += 1
                    _, words = prefix_text(record)
                    censored = record.get("budget_censored") is True or record.get("finish_reason") == "length"
                    if censored:
                        counters["censored_attempts"] += 1
                        diagnostic = diagnostic_censored_label(record)
                        counters["censored_diagnostic_gradeable"] += diagnostic is not None
                        if diagnostic is not None and len(words) >= prefix:
                            counters["censored_diagnostic_prefix_eligible"] += 1
                            root["diagnostic_correct" if diagnostic else "diagnostic_error"] = True
                        continue
                    operational = (record.get("identity_verified") is True and record.get("provider_route_verified") is True
                                   and record.get("observed_trace_status") == "visible_trace_candidate")
                    complete = record.get("status") == "completed" and record.get("finish_reason") == "stop" and operational
                    counters["operational_validation_excluded"] += record.get("status") == "completed" and not operational
                    gradeable = type(record.get("correct")) is bool and record.get("gradable", True) is True
                    if not complete or not gradeable:
                        continue
                    counters["completed_gradeable"] += 1
                    if len(words) >= prefix:
                        counters["eligible_traces"] += 1
                        counters["correct_traces" if record["correct"] else "error_traces"] += 1
                        root["correct" if record["correct"] else "error"] = True
                categories, strata = Counter(), defaultdict(Counter)
                error_roots, correct_roots, mixed_roots = [], [], []
                for root_id, flag in sorted(flags.items()):
                    category = ("mixed" if flag["correct"] and flag["error"] else "correct_only" if flag["correct"]
                                else "error_only" if flag["error"] else "none")
                    categories[category] += 1
                    strata[root_metadata[root_id]][category] += 1
                    if flag["error"]: error_roots.append(root_id)
                    if flag["correct"]: correct_roots.append(root_id)
                    if flag["error"] and flag["correct"]: mixed_roots.append(root_id)
                planned_roots = sorted(flags)
                complete_allocation = counters["recorded_attempts"] == len(indexed) and counters["unknown_attempts"] == 0
                completion_fraction = counters["completed_gradeable"] / len(indexed)
                floor = ROOT_FLOORS["probe"] if stage == "development_probe" else ROOT_FLOORS["source_validation"] if stage == "calibration" else ROOT_FLOORS["target"]
                enough = len(error_roots) >= floor and len(correct_roots) >= floor
                groups.append({"stage": stage, "model": model, "output_budget_tokens": output,
                    "prefix_budget_words": prefix, **dict(counters), "unrecorded_attempts": len(indexed) - counters["recorded_attempts"],
                    "completed_gradeable_fraction_of_planned": completion_fraction,
                    "planned_root_ids": planned_roots, "eligible_root_ids": sorted(set(error_roots) | set(correct_roots)),
                    "error_root_ids": error_roots, "correct_root_ids": correct_roots, "mixed_root_ids": mixed_roots,
                    "planned_roots": len(planned_roots), "error_roots": len(error_roots), "correct_roots": len(correct_roots),
                    "mixed_roots": len(mixed_roots), "categories": {name: categories[name] for name in CATEGORIES},
                    "strata": [{"domain": domain, "tier": tier, "roots": sum(counts.values()),
                                 "categories": {name: counts[name] for name in CATEGORIES}}
                                for (domain, tier), counts in sorted(strata.items())],
                    "censored_diagnostic_error_roots": sum(flag["diagnostic_error"] for flag in flags.values()),
                    "censored_diagnostic_correct_roots": sum(flag["diagnostic_correct"] for flag in flags.values()),
                    "both_observed_classes": bool(error_roots and correct_roots),
                    "class_floor_each": floor, "class_floor_met": enough,
                    "allocation_complete_and_no_unknown": complete_allocation,
                    "engineering_readiness": stage != "historical_development" and complete_allocation and enough and
                                             completion_fraction >= MIN_GRADEABLE_COMPLETION,
                    "error_root_yield_wilson95": wilson_interval(len(error_roots), len(planned_roots)) if complete_allocation else None,
                    "correct_root_yield_wilson95": wilson_interval(len(correct_roots), len(planned_roots)) if complete_allocation else None,
                    "interval_scope": "conditional_iid_root_yield_assumption_not_model_accuracy; fixed_strata_can_be_heterogeneous"})
    primary = [row for row in groups if row["prefix_budget_words"] == PRIMARY_PREFIX_WORDS]
    entire_roster_resolved = all(row["allocation_complete_and_no_unknown"] for row in primary)
    passing_caps = [cap for cap in sorted(output_budgets) if all(
        row["engineering_readiness"] for row in primary if row["output_budget_tokens"] == cap)]
    return {"version": VERSION, "stage": stage, "primary_prefix_words": PRIMARY_PREFIX_WORDS,
            "allow_budget_censored_gradeable": False, "censor": "first exact ANSWER: marker and suffix removed",
            "role_floors": ROOT_FLOORS, "minimum_gradeable_completion_fraction": MIN_GRADEABLE_COMPLETION,
            "planned_generation_attempts": len(indexed) * len(models) * len(output_budgets),
            "groups": groups, "entire_fixed_roster_resolved": entire_roster_resolved,
            "selected_common_output_cap": min(passing_caps) if passing_caps and entire_roster_resolved and stage == "development_probe" else None,
            "cap_selection_rule": "after entire fixed roster resolves with no transport unknown: smallest common cap meeting primary per-model support and >=75% gradeable completion against every planned attempt",
            "selection_scope": "development_engineering_only_not_power_or_final_test_selection",
            "tasks_digest": digest(tasks), "records_digest": digest(records), "E0": "not_passed"}


def pool_root_support(groups):
    require(groups, "No support groups supplied")
    require(len({(group["output_budget_tokens"], group["prefix_budget_words"]) for group in groups}) == 1,
            "Do not pool different output or prefix budgets")
    names = ("planned_root_ids", "eligible_root_ids", "error_root_ids", "correct_root_ids", "mixed_root_ids")
    return {name: sorted({root for group in groups for root in group[name]}) for name in names}


def fold_support(source_train, source_validation, target):
    """Prospective role check; caller supplies exposed/source and final groups."""
    require(len({(group["output_budget_tokens"], group["prefix_budget_words"])
                 for group in source_train + source_validation + target}) == 1,
            "Source and target roles must use the same declared measurement budgets")
    groups = {"source_train": pool_root_support(source_train),
              "source_validation": pool_root_support(source_validation), "target": pool_root_support(target)}
    for first, second in (("source_train", "source_validation"), ("source_train", "target"), ("source_validation", "target")):
        require(not set(groups[first]["planned_root_ids"]) & set(groups[second]["planned_root_ids"]),
                "A root crosses source train/validation/target roles")
    result = {}
    for role, group in groups.items():
        floor = ROOT_FLOORS[role]
        errors, correct = len(group["error_root_ids"]), len(group["correct_root_ids"])
        result[role] = {"error_roots": errors, "correct_roots": correct, "eligible_roots": len(group["eligible_root_ids"]),
                        "floor_each": floor, "floor_met": errors >= floor and correct >= floor}
    return {"roles": result, "class_floor_ready": all(row["floor_met"] for row in result.values()),
            "scope": "policy_floors_only_not_validated_power; source_roots_unioned_across_models_not_duplicated"}


def simulate_support(n_roots, probabilities, floor_each=3, repetitions=2000, seed=20261108):
    """One cell's root-category scenario; paired variants are never new trials."""
    require(type(n_roots) is int and n_roots >= 1 and type(repetitions) is int and repetitions > 0,
            "Positive integer roots and simulation repetitions required")
    require(set(probabilities) == set(CATEGORIES) and all(0 <= value <= 1 for value in probabilities.values())
            and abs(sum(probabilities.values()) - 1) < 1e-12, "Root category probabilities must sum to one")
    require(type(floor_each) is int and floor_each >= 1, "Positive integer support floor required")
    rng = random.Random(seed)
    bounds, total = [], 0.
    for name in CATEGORIES:
        total += probabilities[name]
        bounds.append(total)
    pass_both, pass_error, pass_correct = 0, 0, 0
    for _ in range(repetitions):
        errors = correct = 0
        for _ in range(n_roots):
            category = CATEGORIES[min(bisect_left(bounds, rng.random()), 3)]
            errors += category in ("error_only", "mixed")
            correct += category in ("correct_only", "mixed")
        pass_error += errors >= floor_each
        pass_correct += correct >= floor_each
        pass_both += errors >= floor_each and correct >= floor_each
    p_error = probabilities["error_only"] + probabilities["mixed"]
    p_correct = probabilities["correct_only"] + probabilities["mixed"]
    exact_error, exact_correct = binomial_tail(n_roots, p_error, floor_each), binomial_tail(n_roots, p_correct, floor_each)
    fraction = pass_both / repetitions
    return {"kind": "hypothetical_root_support_scenario_not_observed_data", "n_roots": n_roots,
            "probabilities": probabilities, "floor_each": floor_each, "repetitions": repetitions, "seed": seed,
            "expected_error_roots": n_roots * p_error, "expected_correct_roots": n_roots * p_correct,
            "fraction_joint_support": fraction, "monte_carlo_standard_error": math.sqrt(fraction * (1 - fraction) / repetitions),
            "monte_carlo_fraction_wilson95": wilson_interval(pass_both, repetitions),
            "exact_binomial_error_support": exact_error, "exact_binomial_correct_support": exact_correct,
            "joint_probability_bounds": [max(0., exact_error + exact_correct - 1), min(exact_error, exact_correct)],
            "assumptions": "iid independent original roots with supplied joint category probabilities; per model/output/prefix cell only",
            "limitations": "not joint readiness across dependent model/cap cells; fixed strata may differ; no classifier or error detector was fitted"}


def simulate_paired_loss_precision(n_roots, effect, root_sd, repetitions=2000, seed=20261108,
                                  distribution="normal", rare_event_probability=.05):
    """Illustrative fixed-predictor precision, including a rare-event stress case.

    The normal estimated-SE interval is a planning proxy, not the registered
    bootstrap procedure and not validated power for an actual learned pipeline.
    """
    require(type(n_roots) is int and n_roots >= 2 and root_sd > 0 and math.isfinite(root_sd)
            and math.isfinite(effect) and type(repetitions) is int and repetitions > 0,
            "Finite effect, positive SD, >=2 roots and positive repetitions required")
    require(distribution in ("normal", "rare_event"), "Unknown conditional paired-loss distribution")
    rng, z = random.Random(seed), NormalDist().inv_cdf(.975)
    cdf = []
    if distribution == "rare_event":
        require(0 < rare_event_probability < 1, "Rare-event probability must be in (0,1)")
        cumulative = 0.
        for probability in binomial_probabilities(n_roots, rare_event_probability):
            cumulative += probability
            cdf.append(cumulative)
        cdf[-1] = 1.
    widths, covered, excludes_zero, above_zero, zero_width = [], 0, 0, 0, 0
    for _ in range(repetitions):
        if distribution == "normal":
            estimate = effect + root_sd * rng.gauss(0, 1) / math.sqrt(n_roots)
            sample_sd = root_sd * math.sqrt(rng.gammavariate((n_roots - 1) / 2, 2) / (n_roots - 1))
        else:
            events = bisect_left(cdf, rng.random())
            empirical = events / n_roots
            scaling = math.sqrt(rare_event_probability * (1 - rare_event_probability))
            estimate = effect + root_sd * (empirical - rare_event_probability) / scaling
            sample_sd = root_sd * math.sqrt(n_roots / (n_roots - 1) * empirical * (1 - empirical)) / scaling
        half = z * sample_sd / math.sqrt(n_roots)
        lower, upper = estimate - half, estimate + half
        widths.append(2 * half)
        covered += lower <= effect <= upper
        excludes_zero += lower > 0 or upper < 0
        above_zero += lower > 0
        zero_width += half == 0
    return {"kind": "hypothetical_fixed_predictor_precision_not_validated_power", "n_roots": n_roots,
            "assumed_effect_log_loss_units": effect, "assumed_root_sd": root_sd,
            "distribution": distribution, "rare_event_probability": rare_event_probability if distribution == "rare_event" else None,
            "repetitions": repetitions, "seed": seed, "mean_interval_width": mean(widths), "median_interval_width": median(widths),
            "fraction_covering_assumed_effect": covered / repetitions,
            "fraction_interval_excluding_zero": excludes_zero / repetitions,
            "fraction_interval_above_zero": above_zero / repetitions, "fraction_zero_width_intervals": zero_width / repetitions,
            "interval_proxy": "normal_critical_value_with_estimated_root_SD; not the final bootstrap",
            "limitations": "conditions on fixed predictions and hypothetical root distribution; no training, model selection, eligibility uncertainty or empirical power validation"}


def planning_grid(repetitions=2000, seed=20261108):
    scenarios = {"saturated": {"none": .50, "error_only": .01, "correct_only": .48, "mixed": .01},
                 "moderate": {"none": .25, "error_only": .15, "correct_only": .40, "mixed": .20},
                 "low_eligibility": {"none": .65, "error_only": .10, "correct_only": .15, "mixed": .10}}
    support, precision = [], []
    for n in (24, 48, 96, 192, 384):
        for name, probabilities in scenarios.items():
            for role in ("probe", "target"):
                result = simulate_support(n, probabilities, ROOT_FLOORS[role], repetitions, seed)
                support.append({"scenario": name, "role": role, **result})
        for effect in (0., .01):
            for sd in (.05, .10):
                for distribution in ("normal", "rare_event"):
                    precision.append(simulate_paired_loss_precision(n, effect, sd, repetitions, seed, distribution))
    return {"version": VERSION, "status": "scenario_planning_only_not_observed_or_validated_power",
            "support": support, "precision": precision, "E0": "not_passed",
            "conditional_required_N": required_n_tables(scenarios),
            "sample_size_decision": "not_selected; prospective final protocol must justify utility/effect/precision and budget before drawing new final roots"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    support = commands.add_parser("support")
    support.add_argument("--records", type=Path, required=True)
    support.add_argument("--tasks", type=Path, required=True)
    support.add_argument("--models", required=True)
    support.add_argument("--stage", choices=("development_probe", "calibration", "final_assessment", "historical_development"), default="development_probe")
    support.add_argument("--output-budgets", default="2048,8192")
    support.add_argument("--default-output-budget", type=int)
    support.add_argument("--output", type=Path, required=True)
    simulate = commands.add_parser("simulate")
    simulate.add_argument("--repetitions", type=int, default=2000)
    simulate.add_argument("--seed", type=int, default=20261108)
    simulate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "simulate":
        result = planning_grid(args.repetitions, args.seed)
    else:
        record_document = json.loads(args.records.read_bytes())
        task_document = json.loads(args.tasks.read_bytes())
        records = record_document["records"] if isinstance(record_document, dict) else record_document
        tasks = task_document["tasks"] if isinstance(task_document, dict) else task_document
        if args.stage == "development_probe":
            validate_probe_layout(tasks)
            require(len(args.models.split(",")) == 2 and tuple(sorted(map(int, args.output_budgets.split(",")))) == OUTPUT_BUDGETS,
                    "Registered probe requires two models and output budgets 2048/8192")
        result = summarize_support(records, tasks, args.models.split(","),
                                   tuple(map(int, args.output_budgets.split(","))), stage=args.stage,
                                   explicit_default_output_budget=args.default_output_budget)
        result["input_sha256"] = {"records": hashlib.sha256(args.records.read_bytes()).hexdigest(),
                                  "tasks": hashlib.sha256(args.tasks.read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"output": str(args.output), "version": VERSION, "paid_calls": 0}))


if __name__ == "__main__":
    main()
