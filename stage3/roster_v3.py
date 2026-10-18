"""Development supplement v3. Roster v2 is not replaced and is not a mass pilot."""
import json
from pathlib import Path

from measurement.core import digest, split_manifest
from stage3.baseline_audit import summarize
from stage3.generators_v3 import DOMAINS, FAMILIES, VERSION, generate
from stage3.roster import ROSTER_PATH, canonical, historical_ids, stratum_counts
from stage3.roster_v2 import ROSTER_V2_PATH, V1_SHA

ROSTER_V3_PATH = Path(__file__).resolve().parents[1] / "design" / "PILOT_SECTION_5_5_ROSTER_V3.json"
V2_SHA = "4e0e1df8c009417a197d78c1faf83d93f35097cccea927a885104b37624c9cac"


def specifications():
    specs = []
    for domain in DOMAINS:
        cursor = 0
        for difficulty, count in stratum_counts():
            for offset in range(count):
                family = FAMILIES[domain][cursor % len(FAMILIES[domain])]
                specs.append((domain, family, difficulty, offset))
                cursor += 1
    return specs


def build_tasks():
    return [generate(*spec) for spec in specifications()]


def build_document():
    tasks = build_tasks()
    prompts = [task["prompt"] for task in tasks]
    if len(prompts) != len(set(prompts)) or len({task["root_id"] for task in tasks}) != len(tasks):
        raise ValueError("V3 roster collapsed prompts or roots")
    manifest = split_manifest(tasks, seed=VERSION)
    if any(row["split"] != "development" for row in manifest["tasks"]):
        raise ValueError("V3 task entered confirmatory")
    historical_tasks, historical_roots, historical_prompts = historical_ids()
    v1 = json.loads(ROSTER_PATH.read_bytes())
    v2 = json.loads(ROSTER_V2_PATH.read_bytes())
    if v1["roster_sha256"] != V1_SHA or v2["roster_sha256"] != V2_SHA:
        raise ValueError("Earlier rosters drifted")
    own = {task["task_id"] for task in tasks}
    own_roots = {task["root_id"] for task in tasks}
    own_prompts = {row["prompt_sha256"] for row in manifest["tasks"]}
    for left, right in (
        (own, historical_tasks), (own_roots, historical_roots), (own_prompts, historical_prompts),
        (own, {task["task_id"] for task in v1["tasks"]}), (own, {task["task_id"] for task in v2["tasks"]}),
        (own_prompts, {row["prompt_sha256"] for row in v2["split_manifest"]["tasks"]}),
    ):
        if left & right:
            raise ValueError("V3 roster overlaps an earlier corpus")
    audit = summarize(tasks)
    if audit["family_majority_accuracy"] > 0.6 or audit["logic_always_unsat"] > 0.55:
        raise ValueError("V3 labels are still predicted by family or a constant")
    if audit["math"]["easy_with_multiplication"] != 0 or audit["math"]["hard_with_extra_structure"] != audit["math"]["hard_count"]:
        raise ValueError("V3 math difficulty does not change the operation")
    document = {
        "schema_version": 1,
        "status": "development_supplement_not_executed",
        "stage3_started": False,
        "mass_pilot_authorized": False,
        "does_not_replace": ["design/PILOT_SECTION_5_5_ROSTER.json", "design/PILOT_SECTION_5_5_ROSTER_V2.json"],
        "generator_version": VERSION,
        "E0": "not_passed",
        "paid_calls": 0,
        "task_count": len(tasks),
        "root_count": len(own_roots),
        "baseline_audit": audit,
        "confirmatory_excluded": True,
        "models_executed": [],
        "split_manifest": manifest,
        "tasks": sorted(tasks, key=lambda task: task["task_id"]),
    }
    document["roster_sha256"] = digest({key: value for key, value in document.items() if key != "roster_sha256"})
    return document


def validate(document):
    if document.get("mass_pilot_authorized") is not False or document.get("E0") != "not_passed":
        raise ValueError("V3 roster authorizes a pilot or passes E0")
    body = {key: value for key, value in document.items() if key != "roster_sha256"}
    if document.get("roster_sha256") != digest(body):
        raise ValueError("V3 roster digest mismatch")
    fresh = build_document()
    if fresh["roster_sha256"] != document["roster_sha256"]:
        raise ValueError("V3 roster differs from the builder")
    return {"status": document["status"], "tasks": document["task_count"], "roots": document["root_count"],
            "family_majority_accuracy": document["baseline_audit"]["family_majority_accuracy"],
            "logic_always_unsat": document["baseline_audit"]["logic_always_unsat"],
            "mass_pilot_authorized": False}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if args.write:
        args.write.write_bytes(canonical(build_document()) + b"\n")
        print(json.dumps({"wrote": str(args.write), "bytes": args.write.stat().st_size}))
    elif args.check:
        print(json.dumps(validate(json.loads(args.check.read_bytes())), indent=2))
    else:
        parser.error("Choose --write or --check")


if __name__ == "__main__":
    main()
