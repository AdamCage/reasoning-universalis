"""Pin a completed pilot-v2 artifact roster for the frozen integrity adapter.

This command performs no experiment, model request, scientific review or kernel
operation. Run only after final collection, support, cost and decision artifacts
exist. It writes one explicit index and never changes an indexed input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_file(value, root=ROOT):
    path = Path(value)
    path = path if path.is_absolute() else root / path
    require(not path.is_symlink(), "Symlink input is forbidden")
    path = path.resolve(strict=True)
    require(path.is_file() and path.is_relative_to(root), "Input must be a plain project file")
    return path


def read_json(path):
    return json.loads(path.read_bytes())


def build_index(*, scope, protocol, tasks, results, support, cost, future_decision,
                extra=(), root=ROOT):
    root = Path(root).resolve(strict=True)
    scope = Path(scope)
    scope = (scope if scope.is_absolute() else root / scope).resolve(strict=True)
    require(scope.is_dir() and scope.is_relative_to(root), "Scope must be inside the research checkout")
    paths = {name: local_file(value, root) for name, value in {
        "protocol": protocol, "tasks": tasks, "results": results, "support": support,
        "cost": cost, "future_decision": future_decision}.items()}
    p, corpus, observed, supported = (read_json(paths[name]) for name in
                                      ("protocol", "tasks", "results", "support"))
    protocol_sha, corpus_sha = sha(paths["protocol"].read_bytes()), sha(paths["tasks"].read_bytes())
    require((scope / "protocol.json").read_bytes() == paths["protocol"].read_bytes(), "Scope/public protocol mismatch")
    require((scope / "corpus.json").read_bytes() == paths["tasks"].read_bytes(), "Scope/public corpus mismatch")
    require(scope.name == protocol_sha and p["tasks"]["file_sha256"] == corpus_sha,
            "Protocol/scope/corpus pins disagree")
    require(corpus.get("status") == "development_only_not_confirmatory"
            and len(corpus["tasks"]) == 48 and len({t["root_id"] for t in corpus["tasks"]}) == 24,
            "Expected the frozen development-only 48-task/24-root corpus")
    require(observed.get("protocol_sha256") == protocol_sha and observed.get("corpus_sha256") == corpus_sha,
            "Results do not belong to the frozen protocol and corpus")
    require(observed.get("all_planned_cells") == 192 and len(observed["records"]) == 192,
            "Final results must represent every planned cell, including unsent cells")
    planned = {(t["task_id"], m["model"], cap) for t in corpus["tasks"] for m in p["models"]
               for cap in p["generation"]["output_budget_tokens"]}
    represented = [(r["task_id"], r["model"], r["output_budget_tokens"]) for r in observed["records"]]
    require(len(set(represented)) == len(represented) and set(represented) == planned,
            "Result rows do not exactly match the fixed planned task/model/cap matrix")
    require(observed.get("E0") == "not_passed" and observed.get("scientific_validity") == "not_assessed",
            "Results must preserve unresolved E0 and scientific validity")
    require(supported.get("tasks_digest") == sha(canonical(corpus["tasks"]))
            and supported.get("records_digest") == sha(canonical(observed["records"])),
            "Support table is not linked to these exact task and result records")
    require(supported.get("planned_generation_attempts") == 192 and supported.get("primary_prefix_words") == 256
            and supported.get("allow_budget_censored_gradeable") is False and supported.get("E0") == "not_passed",
            "Support table changed the registered denominator, primary prefix or censoring rule")
    inventory_path = local_file(scope / "source-inventory.json", root)
    inventory = read_json(inventory_path)
    require(observed.get("source_inventory_sha256") == sha(inventory_path.read_bytes()),
            "Results/source inventory mismatch")
    rows, seen, empty = [], set(), []
    def add(path, role):
        path = local_file(path, root)
        relative = path.relative_to(root).as_posix()
        require(relative not in seen, "Duplicate artifact path: " + relative)
        data = path.read_bytes()
        require(bool(data), "The frozen evidence pack requires nonempty inputs: " + relative)
        form = "json" if path.suffix == ".json" else "bytes"
        if form == "json": json.loads(data)
        rows.append({"path": relative, "role": role, "format": form,
                     "sha256": sha(data), "bytes": len(data)})
        seen.add(relative)
    for name, path in paths.items():
        add(path, name)
    for relative, expected in sorted(inventory["files"].items()):
        current, frozen = local_file(relative, root), local_file(scope / "source" / relative, root)
        require(sha(current.read_bytes()) == expected and frozen.read_bytes() == current.read_bytes(),
                "Frozen source differs from current indexed source: " + relative)
        if current.stat().st_size:
            add(current, "source")
        else:
            empty.append({"path": relative, "sha256": expected,
                          "reason": "Empty source is retained by the indexed inventory; pack forbids empty individual artifacts"})
    add(inventory_path, "source_inventory")
    add(scope / "dispatch-plan.json", "dispatch_plan")
    add(scope / "cost-plan.json", "prospective_cost_plan")
    add(scope / "ledger-launch.json", "launch_ledger")
    for path in extra:
        add(path, "supplementary")
    return {"schema_version": 1, "purpose": "pilot_v2_completed_artifact_integrity_index",
        "scope": "Previously observed development artifacts; exact byte integrity only. The offline primary/reanalysis jobs hash indexed artifacts and do not independently rerun the support analysis.",
        "scientific_validity": "not_assessed", "review": "not_requested", "E0": "not_passed",
        "registered_after_collection": True, "protocol_sha256": protocol_sha,
        "corpus_file_sha256": corpus_sha, "source_inventory_sha256": sha(inventory_path.read_bytes()),
        "empty_source_files_retained_in_inventory": empty, "artifacts": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("scope", "protocol", "tasks", "results", "support", "cost", "future-decision", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--extra", type=Path, action="append", default=[])
    args = parser.parse_args()
    document = build_index(scope=args.scope, protocol=args.protocol, tasks=args.tasks,
        results=args.results, support=args.support, cost=args.cost, future_decision=args.future_decision, extra=args.extra)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    require(output.resolve().is_relative_to(ROOT), "Output must stay inside the research checkout")
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        require(output.read_bytes() == payload, "Refusing to overwrite a different evidence index")
    else:
        with output.open("xb") as stream: stream.write(payload)
    print(json.dumps({"output": str(output), "sha256": sha(payload), "input_artifacts": len(document["artifacts"]),
                      "kernel_calls": 0, "model_calls": 0, "scientific_validity": "not_assessed"}))


if __name__ == "__main__":
    main()
