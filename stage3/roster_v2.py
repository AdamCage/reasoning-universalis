"""Candidate §5.5 roster from stage3-generators-v2. Not executed.

The v1 roster remains a development artifact. Its twelve template roots are not
this roster. No model call and no confirmatory split is created here.
"""
import json
from pathlib import Path

from measurement.core import digest, split_manifest
from stage3.generators_v2 import DOMAINS, FAMILIES, VERSION, generate, solve, verify
from stage3.roster import ROSTER_PATH, canonical, historical_ids, stratum_counts

ROSTER_V2_PATH = Path(__file__).resolve().parents[1] / "design" / "PILOT_SECTION_5_5_ROSTER_V2.json"
V1_SHA = "a7d8aa5f4dd6d15f7a8b2392d5d2bcd25b7c74431e7f9bb0c081cf548faf0f7d"


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
    tasks = [generate(domain, family, difficulty, seed) for domain, family, difficulty, seed in specifications()]
    if len(tasks) != len({task["task_id"] for task in tasks}) or len({task["root_id"] for task in tasks}) != len(tasks):
        raise ValueError("Stage 3 roster collapsed independent structures")
    return tasks


def _ids(document):
    return {row["task_id"] for row in document["tasks"]}, {row["root_id"] for row in document["tasks"]}, {
        row["prompt_sha256"] for row in document["split_manifest"]["tasks"]}


def build_document():
    tasks = build_tasks()
    manifest = split_manifest(tasks, seed=VERSION)
    if any(row["split"] != "development" for row in manifest["tasks"]):
        raise ValueError("Stage 3 task entered confirmatory")
    historical_tasks, historical_roots, historical_prompts = historical_ids()
    v1 = json.loads(ROSTER_PATH.read_bytes())
    if v1["roster_sha256"] != V1_SHA:
        raise ValueError("Stage 3 roster lost the pinned v1 development artifact")
    own_tasks, own_roots, own_prompts = (
        {task["task_id"] for task in tasks},
        {task["root_id"] for task in tasks},
        {row["prompt_sha256"] for row in manifest["tasks"]},
    )
    for label, left, right in (
        ("Historical task", own_tasks, historical_tasks),
        ("Historical root", own_roots, historical_roots),
        ("Historical prompt", own_prompts, historical_prompts),
        ("V1 task", own_tasks, {task["task_id"] for task in v1["tasks"]}),
        ("V1 root", own_roots, {task["root_id"] for task in v1["tasks"]}),
        ("V1 prompt", own_prompts, {row["prompt_sha256"] for row in v1["split_manifest"]["tasks"]}),
    ):
        shared = left & right
        if shared:
            raise ValueError(label + " overlap")
    logic = [task for task in tasks if task["domain"] == "logic"]
    sat = sum(solve(task) == "SAT" for task in logic)
    algorithms = [task for task in tasks if task["domain"] == "algorithms"]
    identity_hits = sum(verify(task, "ANSWER: " + json.dumps(list(range(task["data"]["nodes"]))))["verdict"] == "correct"
                        for task in algorithms)
    document = {
        "schema_version": 1,
        "status": "preregistered_not_executed",
        "stage3_started": False,
        "mass_pilot_authorized": False,
        "supersedes_development_roster": "design/PILOT_SECTION_5_5_ROSTER.json",
        "superseded_roster_sha256": V1_SHA,
        "generator_version": VERSION,
        "pilot_section": "5.5",
        "E0": "not_passed",
        "G2": "not_frozen",
        "scientific_validity": "not_assessed",
        "paid_calls": 0,
        "task_count": len(tasks),
        "root_count": len(own_roots),
        "root_rule": "One root per structural instance. Parameter variants of that instance would share the root; different seeds do not.",
        "confirmatory_excluded": True,
        "logic_sat_count": sat,
        "logic_task_count": len(logic),
        "identity_topo_baseline_correct": identity_hits,
        "models_executed": [],
        "generations_executed": 0,
        "split_manifest": manifest,
        "tasks": sorted(tasks, key=lambda task: task["task_id"]),
    }
    document["roster_sha256"] = digest({key: value for key, value in document.items() if key != "roster_sha256"})
    return document


def validate(document):
    if document.get("mass_pilot_authorized") is not False or document.get("stage3_started") is not False:
        raise ValueError("Roster authorizes a live pilot")
    if document.get("E0") != "not_passed" or document.get("paid_calls") != 0:
        raise ValueError("Roster records E0 or a paid call")
    if document.get("root_count") != document.get("task_count") or document.get("task_count") != 200:
        raise ValueError("Structural roots collapsed")
    if document.get("logic_sat_count") / document.get("logic_task_count") > 0.45:
        raise ValueError("Logic roster is still dominated by SAT")
    if document.get("identity_topo_baseline_correct") != 0:
        raise ValueError("Identity topological baseline still solves the algorithm roster")
    body = {key: value for key, value in document.items() if key != "roster_sha256"}
    if document.get("roster_sha256") != digest(body):
        raise ValueError("Roster digest mismatch")
    fresh = build_document()
    if fresh["roster_sha256"] != document["roster_sha256"]:
        raise ValueError("Roster differs from the registered builder")
    return {"status": document["status"], "tasks": 200, "roots": 200, "logic_sat_count": document["logic_sat_count"],
            "mass_pilot_authorized": False, "E0": "not_passed"}


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
