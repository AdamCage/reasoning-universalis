"""Development supplement v4. Earlier rosters stay published and unchanged."""
import json
from pathlib import Path

from measurement.core import digest, split_manifest
from stage3.baseline_audit import surface_audit
from stage3.generators_v4 import DOMAINS, FAMILIES, VERSION, generate
from stage3.roster import ROSTER_PATH, canonical, historical_ids, stratum_counts
from stage3.roster_v2 import ROSTER_V2_PATH, V1_SHA
from stage3.roster_v3 import ROSTER_V3_PATH

ROSTER_V4_PATH = Path(__file__).resolve().parents[1] / "design" / "PILOT_SECTION_5_5_ROSTER_V4.json"
V2_SHA = "4e0e1df8c009417a197d78c1faf83d93f35097cccea927a885104b37624c9cac"
V3_SHA = "17f410cf6262adf7af6b58c5a7233cf4206e107463348213969fdb19ebe223eb"


def specifications():
    specs = []
    for domain in DOMAINS:
        cursor = 0
        for difficulty, count in stratum_counts():
            for offset in range(count):
                specs.append((domain, FAMILIES[domain][cursor % 3], difficulty, offset))
                cursor += 1
    return specs


def build_tasks():
    return [generate(*spec) for spec in specifications()]


def _overlap(left, right):
    return bool(set(left) & set(right))


def build_document():
    tasks = build_tasks()
    if len({task["prompt"] for task in tasks}) != len(tasks) or len({task["root_id"] for task in tasks}) != len(tasks):
        raise ValueError("V4 roster collapsed prompts or roots")
    manifest = split_manifest(tasks, seed=VERSION)
    if any(row["split"] != "development" for row in manifest["tasks"]):
        raise ValueError("V4 task entered confirmatory")
    historical_tasks, historical_roots, historical_prompts = historical_ids()
    earlier = [json.loads(path.read_bytes()) for path in (ROSTER_PATH, ROSTER_V2_PATH, ROSTER_V3_PATH)]
    if (earlier[0]["roster_sha256"], earlier[1]["roster_sha256"], earlier[2]["roster_sha256"]) != (V1_SHA, V2_SHA, V3_SHA):
        raise ValueError("Published development rosters drifted")
    own = {task["task_id"] for task in tasks}
    own_roots = {task["root_id"] for task in tasks}
    own_prompts = {row["prompt_sha256"] for row in manifest["tasks"]}
    for document in earlier:
        if _overlap(own, (task["task_id"] for task in document["tasks"])):
            raise ValueError("V4 task id repeats an earlier roster")
        if _overlap(own_roots, (task["root_id"] for task in document["tasks"])):
            raise ValueError("V4 root repeats an earlier roster")
        if _overlap(own_prompts, (row["prompt_sha256"] for row in document["split_manifest"]["tasks"])):
            raise ValueError("V4 prompt repeats an earlier roster")
    if _overlap(own, historical_tasks) or _overlap(own_roots, historical_roots) or _overlap(own_prompts, historical_prompts):
        raise ValueError("V4 overlaps the historical Stage 0 roots")
    audit = surface_audit(tasks)
    for key in ("family_majority_accuracy", "seed_parity_accuracy", "prompt_length_accuracy", "structure_count_accuracy"):
        if audit[key] > 0.7:
            raise ValueError("V4 surface feature still predicts the label: " + key)
    document = {
        "schema_version": 1,
        "status": "development_supplement_not_executed",
        "stage3_started": False,
        "mass_pilot_authorized": False,
        "keeps_published_rosters": [
            "design/PILOT_SECTION_5_5_ROSTER.json",
            "design/PILOT_SECTION_5_5_ROSTER_V2.json",
            "design/PILOT_SECTION_5_5_ROSTER_V3.json",
        ],
        "generator_version": VERSION,
        "E0": "not_passed",
        "paid_calls": 0,
        "task_count": len(tasks),
        "root_count": len(own_roots),
        "surface_audit": audit,
        "confirmatory_excluded": True,
        "models_executed": [],
        "split_manifest": manifest,
        "tasks": sorted(tasks, key=lambda task: task["task_id"]),
    }
    document["roster_sha256"] = digest({key: value for key, value in document.items() if key != "roster_sha256"})
    return document


def validate(document):
    if document.get("mass_pilot_authorized") is not False or document.get("E0") != "not_passed":
        raise ValueError("V4 roster authorizes a pilot or passes E0")
    body = {key: value for key, value in document.items() if key != "roster_sha256"}
    if document.get("roster_sha256") != digest(body):
        raise ValueError("V4 roster digest mismatch")
    fresh = build_document()
    if fresh["roster_sha256"] != document["roster_sha256"]:
        raise ValueError("V4 roster differs from the builder")
    return {"status": document["status"], "tasks": 200, "roots": 200,
            "surface_audit": document["surface_audit"], "mass_pilot_authorized": False, "E0": "not_passed"}


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
