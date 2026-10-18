"""Preregister the §5.5 pilot task roster without a model call.

Stage 2 `generate` stamps every fresh id as already observed. This registrar
keeps that generator untouched, records its digest as lineage, and publishes
an explicit pilot manifest whose every root is excluded from confirmatory.
Publishing the prompts is the exposure event. No trace is executed here.
"""
import json
from pathlib import Path

from measurement.core import digest, split_manifest
from stage2.datasets import DOMAINS, generate

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "design" / "historical-development-manifest.json"
ROSTER_PATH = ROOT / "design" / "PILOT_SECTION_5_5_ROSTER.json"
VERSION = "pilot-section-5.5-roster-v1"
TASKS_PER_DOMAIN = 50
STRATA = ("easy", "medium", "hard")
PROPOSED_MODELS = (
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
    "deepseek/deepseek-v4.1-flash",
)
ADMITTED_FULL_TRACE = "openai/gpt-oss-20b"


def stratum_counts(tasks_per_domain=TASKS_PER_DOMAIN):
    if tasks_per_domain < len(STRATA):
        raise ValueError("Pilot roster needs at least one task in each solver stratum")
    base, remainder = divmod(tasks_per_domain, len(STRATA))
    return tuple((name, base + (1 if index < remainder else 0)) for index, name in enumerate(STRATA))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def mint(domain, difficulty, seed):
    raw = generate(domain, seed, difficulty)
    task = {key: value for key, value in raw.items() if key != "task_digest"}
    task.update(
        previously_observed=True,
        forced_split="development",
        exposure="published_in_pilot_roster",
        cohort=VERSION,
        confirmatory_excluded=True,
        pilot_section="5.5",
        executed=False,
        source_generator="stage2.datasets.generate",
        source_task_digest=raw["task_digest"],
    )
    task["task_digest"] = digest({key: value for key, value in task.items() if key != "task_digest"})
    return task


def build_tasks():
    tasks = []
    for domain in DOMAINS:
        for difficulty, count in stratum_counts():
            tasks.extend(mint(domain, difficulty, seed) for seed in range(count))
    if len(tasks) != len(DOMAINS) * TASKS_PER_DOMAIN:
        raise ValueError("Pilot roster does not match §5.5 task count")
    return tasks


def historical_ids():
    document = json.loads(HISTORICAL.read_bytes())
    return {row["task_id"] for row in document["tasks"]}, {row["root_id"] for row in document["tasks"]}, {
        row["prompt_sha256"] for row in document["tasks"]
    }


def assert_disjoint(left_ids, right_ids, label):
    shared = set(left_ids) & set(right_ids)
    if shared:
        raise ValueError(label + " overlap: " + ",".join(sorted(shared)[:5]))


def build_document(tasks=None):
    tasks = build_tasks() if tasks is None else tasks
    manifest = split_manifest(tasks, seed=VERSION)
    if any(row["split"] != "development" for row in manifest["tasks"]):
        raise ValueError("Pilot task entered confirmatory or measurement-validation")
    task_ids = {task["task_id"] for task in tasks}
    root_ids = {task["root_id"] for task in tasks}
    prompt_hashes = {row["prompt_sha256"] for row in manifest["tasks"]}
    historical_tasks, historical_roots, historical_prompts = historical_ids()
    assert_disjoint(task_ids, historical_tasks, "Historical task")
    assert_disjoint(root_ids, historical_roots, "Historical root")
    assert_disjoint(prompt_hashes, historical_prompts, "Historical prompt")
    by_domain = {}
    for task in tasks:
        by_domain.setdefault(task["domain"], []).append(task)
    if set(by_domain) != set(DOMAINS) or any(len(rows) != TASKS_PER_DOMAIN for rows in by_domain.values()):
        raise ValueError("Domain roster differs from §5.5")
    document = {
        "schema_version": 1,
        "status": "preregistered_not_executed",
        "stage3_started": False,
        "pilot_section": "5.5",
        "E0": "not_passed",
        "G2": "not_frozen",
        "scientific_validity": "not_assessed",
        "paid_calls": 0,
        "starter_design": {
            "domains": 4,
            "tasks_per_domain": TASKS_PER_DOMAIN,
            "models": 3,
            "generations_per_task": 3,
            "trace_upper_bound": 1800,
        },
        "strata_rule": "Integer partition of 50 across easy, medium, hard in that order; remainder goes to the earlier strata. Solver bounds stay the Stage 2 generator bounds. This is not a confirmatory difficulty definition.",
        "stratum_counts_per_domain": {name: count for name, count in stratum_counts()},
        "root_rule": "Stage 2 conservative template: one root per domain and solver stratum. Fifty tasks in a domain are not fifty independent roots.",
        "root_count": len(root_ids),
        "task_count": len(tasks),
        "confirmatory_excluded": True,
        "historical_stage0_disjoint": True,
        "models_executed": [],
        "generations_executed": 0,
        "only_stage0_full_trace_admission": ADMITTED_FULL_TRACE,
        "proposed_models": list(PROPOSED_MODELS),
        "models_not_admitted": [model for model in PROPOSED_MODELS if model != ADMITTED_FULL_TRACE],
        "split_manifest": manifest,
        "tasks": sorted(tasks, key=lambda task: task["task_id"]),
    }
    document["roster_sha256"] = digest({key: value for key, value in document.items() if key != "roster_sha256"})
    return document


def roster_bytes(document=None):
    return canonical(build_document() if document is None else document) + b"\n"


def validate(document):
    if document.get("status") != "preregistered_not_executed" or document.get("stage3_started") is not False:
        raise ValueError("Pilot roster claims execution")
    if document.get("E0") != "not_passed" or document.get("G2") != "not_frozen":
        raise ValueError("Pilot roster passes E0 or freezes G2")
    if document.get("paid_calls") != 0 or document.get("generations_executed") != 0 or document.get("models_executed") != []:
        raise ValueError("Pilot roster records a live run")
    if document.get("scientific_validity") != "not_assessed" or document.get("confirmatory_excluded") is not True:
        raise ValueError("Pilot roster changes scientific status")
    body = {key: value for key, value in document.items() if key != "roster_sha256"}
    if document.get("roster_sha256") != digest(body):
        raise ValueError("Pilot roster digest mismatch")
    fresh = build_document()
    if fresh["roster_sha256"] != document["roster_sha256"]:
        raise ValueError("Pilot roster differs from the registered builder")
    if any(row["split"] != "development" for row in document["split_manifest"]["tasks"]):
        raise ValueError("Pilot task is not excluded from confirmatory")
    if any(task.get("confirmatory_excluded") is not True or task.get("executed") is not False for task in document["tasks"]):
        raise ValueError("Pilot task exposure flags changed")
    return {
        "status": document["status"],
        "tasks": document["task_count"],
        "roots": document["root_count"],
        "E0": document["E0"],
        "paid_calls": 0,
        "stage3_started": False,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if args.write:
        args.write.write_bytes(roster_bytes())
        print(json.dumps({"wrote": str(args.write), "bytes": args.write.stat().st_size}))
    elif args.check:
        print(json.dumps(validate(json.loads(args.check.read_bytes())), indent=2))
    else:
        parser.error("Choose --write or --check")


if __name__ == "__main__":
    main()
