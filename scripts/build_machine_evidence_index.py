"""Index CLOSED machine-only artifacts for the pinned EpistemeOS hash stage.

No model, kernel, scientific-review or statistical-analysis work occurs here.
Use an explicitly copied final ledger; the live shared ledger is never read.
The later adapter hashes these bytes twice, not independent scientific data.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_CAPTURE_BYTES = 40 * 1024 * 1024
FORMAT = "reasoning-universalis-machine-development-delta-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def local_file(value, root):
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else root / candidate
    require(not candidate.is_symlink() and candidate.name != ".env", "Unsafe or private index input")
    candidate = candidate.resolve(strict=True)
    require(candidate.is_file() and candidate.is_relative_to(root) and ".git" not in candidate.relative_to(root).parts,
            "Evidence input must remain a plain project file")
    return candidate


def source_relative(value):
    path = PurePosixPath(value)
    require(isinstance(value, str) and "\\" not in value and path.parts and not path.is_absolute()
            and path.as_posix() == value and all(part not in (".", "..") and ":" not in part for part in path.parts),
            "Unsafe frozen source path")
    return path


def build_index(*, scope, protocol, inputs, results, summary, budget, ledger_snapshot,
                export_manifest, reproduction, extra=(), root=ROOT):
    root = Path(root).resolve(strict=True)
    scope = Path(scope)
    scope = (scope if scope.is_absolute() else root / scope).resolve(strict=True)
    require(scope.is_dir() and scope.is_relative_to(root) and scope.parent.name == "machine-development",
            "Use the existing machine-development scope")
    paths = {name: local_file(value, root) for name, value in {
        "protocol": protocol, "tasks": inputs, "results": results, "summary": summary,
        "budget": budget, "final_ledger": ledger_snapshot, "export_manifest": export_manifest,
        "reproduction": reproduction}.items()}
    # Reject this spelling before opening it. There is no read-only exception
    # for a live Windows ledger handle outside the cooperative budget lock.
    live_ledger = scope.parent.parent / "ledger.json"
    require(paths["final_ledger"] != live_ledger.resolve(), "Supply a copied FINAL ledger, never the live ledger")
    p, items_doc, observed, supported, accounting, ledger, bundle, replay = (
        load(paths[name]) for name in ("protocol", "tasks", "results", "summary", "budget",
                                      "final_ledger", "export_manifest", "reproduction"))
    protocol_sha, inputs_sha = sha(paths["protocol"].read_bytes()), sha(paths["tasks"].read_bytes())
    require(p.get("status") == "prospective_frozen_machine_development" and scope.name == protocol_sha,
            "Machine protocol/scope is not the frozen measured condition")
    require((scope / "protocol.json").read_bytes() == paths["protocol"].read_bytes()
            and (scope / "items.json").read_bytes() == paths["tasks"].read_bytes()
            and p["inputs"]["file_sha256"] == inputs_sha, "Public/bound machine protocol or input differs")
    items = items_doc["items"]
    identities = {item["item_id"] for item in items}
    require(len(items) == len(identities) == p["inputs"]["items"] == 200 and p["inputs"]["roots"] == 24,
            "The accepted full200-item/24-root condition changed")
    require(len(items_doc["audit_item_ids"]) == 20 and set(items_doc["audit_item_ids"]) <= identities,
            "The fixed audit denominator changed")
    plan_path, inventory_path, launch_path = (local_file(scope / name, root) for name in
        ("dispatch-plan.json", "source-inventory.json", "ledger-launch.json"))
    plan, inventory, launch = load(plan_path), load(inventory_path), load(launch_path)
    inventory_sha = sha(inventory_path.read_bytes())
    require(p["source_freeze"]["expected_source_inventory_sha256"] == inventory_sha
            and observed["source_inventory_sha256"] == inventory_sha == plan["source_inventory_sha256"],
            "Machine source inventory is not its pre-data binding")
    require(observed.get("phase") == "machine_development_annotation"
            and observed.get("protocol_sha256") == protocol_sha
            and observed.get("items_sha256") == inputs_sha
            and observed.get("dispatch_plan_sha256") == sha(plan_path.read_bytes())
            and observed.get("maximum_calls") == p["allocation"]["maximum_calls"] == 2100,
            "Closed machine results do not belong to the full frozen roster")
    closed = datetime.fromisoformat(observed["completed_utc"].replace("Z", "+00:00"))
    require(closed.tzinfo is not None, "Final collection timestamp is missing its timezone")
    require((scope / "results.json").read_bytes() == paths["results"].read_bytes(),
            "Use the exact closed machine result copy")
    planned, represented = plan["cells"], observed["all_planned_calls"]
    require(len(planned) == len(represented) == 2100
            and len({cell["call_id"] for cell in planned}) == 2100
            and [row["call_id"] for row in represented] == [row["call_id"] for row in planned],
            "Final registry lost requested, conditional, audit or unsent cells")
    require(len(observed["items"]) == 200 and {row["item_id"] for row in observed["items"]} == identities
            and set(observed["audits"]) == set(items_doc["audit_item_ids"]), "Primary/audit item registry changed")
    for result in (observed, supported):
        require(result.get("E0") == "not_passed" and result.get("human_gold") == "not_created"
                and result.get("scientific_validity") == "not_assessed", "Machine annotations were promoted to human/scientific acceptance")
    require(supported["planned_items"] == 200 and supported["distinct_root_blocks"] == 24
            and supported["accuracy_estimated"] is False and supported["audit_updates_primary"] is False
            and supported["protocol_sha256"] == protocol_sha
            and supported["call_coverage"]["all_planned_slots"] == 2100,
            "Summary changed its machine-only scope or planned denominator")
    pins = supported["input_sha256"]
    require(pins["protocol"] == protocol_sha and pins["items"] == inputs_sha
            and pins["results"] == sha(paths["results"].read_bytes())
            and pins["inventory"] == inventory_sha and pins["plan"] == sha(plan_path.read_bytes())
            and pins["ledger"] == sha(paths["final_ledger"].read_bytes())
            and pins["launch_ledger"] == sha(launch_path.read_bytes()), "Summary pins refer to different final artifacts")
    parent = p["parent"]
    require(len(launch) == parent["launch_ledger_rows"] == 984
            and sha(launch_path.read_bytes()) == parent["launch_ledger_sha256"]
            and ledger[:len(launch)] == launch and len({row["id"] for row in ledger}) == len(ledger),
            "Final copied ledger did not retain the exact 984-row parent prefix")
    amounts = [Decimal(row["charged_or_reserved_rub"]) for row in ledger]
    require(all(amount.is_finite() and amount >= 0 for amount in amounts), "Invalid final ledger obligation")
    total = sum(amounts, Decimal(0))
    require(Decimal(observed["charged_or_reserved_rub"]) == total
            and accounting["launch_prefix_preserved"] is True
            and accounting["launch"]["rows"] == 984 and accounting["final"]["rows"] == len(ledger)
            and Decimal(accounting["final"]["charged_or_reserved_rub"]) == total,
            "Final result, summary budget and copied ledger are not synchronized")
    require(bundle.get("format") == FORMAT and bundle["payload"]["protocol_sha256"] == protocol_sha
            and bundle["payload"]["source_inventory_sha256"] == inventory_sha, "Raw export manifest belongs to another condition")
    require(replay.get("status") == "passed" and replay.get("network_attempts") == 0
            and replay.get("results_exact") is True and replay.get("summary_exact") is True
            and replay["bundle_manifest_sha256"] == sha(paths["export_manifest"].read_bytes())
            and replay["results_sha256"] == sha(paths["results"].read_bytes())
            and replay["summary_sha256"] == sha(paths["summary"].read_bytes()),
            "A passed zero-network exact raw-export replay receipt is required")
    rows, seen, empty = [], set(), []
    def add(value, role):
        path = local_file(value, root)
        relative = path.relative_to(root).as_posix()
        require(relative not in seen and path != live_ledger.resolve(), "Duplicate or live-ledger index input")
        data = path.read_bytes()
        require(data, "Empty individual evidence inputs are forbidden")
        form = "json" if path.suffix == ".json" else "bytes"
        if form == "json":
            load(path)
        rows.append({"path": relative, "role": role, "format": form, "sha256": sha(data), "bytes": len(data)})
        seen.add(relative)
    for name, path in paths.items():
        add(path, name)
    for name, digest in sorted(inventory["files"].items()):
        relative = source_relative(name)
        snapshot = local_file(scope / "source" / relative, root)
        data = snapshot.read_bytes()
        require(sha(data) == digest, "Frozen exact source snapshot differs: " + name)
        if data:
            add(snapshot, "source")
        else:
            empty.append({"source_path": name, "snapshot_path": snapshot.relative_to(root).as_posix(),
                          "sha256": digest, "reason": "Exact empty source retained by indexed inventory; kernel pack forbids empty CAS inputs"})
    for path, role in ((inventory_path, "source_inventory"), (plan_path, "dispatch_plan"),
                       (launch_path, "launch_ledger"), (scope / "cost-plan.json", "prospective_worst_case_cost_plan")):
        add(path, role)
    for name in ("codebook", "mapping", "annotation_config", "route_metadata", "license_receipt"):
        path = scope / (name + ".json")
        if path.is_file():
            add(path, "bound_" + name)
    for path in extra:
        add(path, "postdata_supplementary")
    require(sum(row["bytes"] for row in rows) < MAX_CAPTURE_BYTES,
            "Explicit capture exceeds the conservative kernel-CAS envelope; do not silently trim evidence")
    return {"schema_version": 1, "purpose": "machine_development_completed_artifact_integrity_index",
            "registered_after_collection": True, "protocol_sha256": protocol_sha, "items_sha256": inputs_sha,
            "source_inventory_sha256": inventory_sha, "closed_utc": closed.isoformat(),
            "scope": "Exact postcollection byte hashes only; primary/reanalysis hash jobs share data and author, without independent statistical recomputation",
            "source_scope": "Actual frozen scope/source bytes, including CRLF; current Git LF files are not substituted",
            "scientific_validity": "not_assessed", "review": "not_requested", "E0": "not_passed",
            "human_gold": "not_created", "empty_source_files_retained_in_inventory": empty,
            "artifacts": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("scope", "protocol", "inputs", "results", "summary", "budget", "ledger-snapshot",
                 "export-manifest", "reproduction", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--extra", type=Path, action="append", default=[])
    args = parser.parse_args()
    result = build_index(scope=args.scope, protocol=args.protocol, inputs=args.inputs, results=args.results,
        summary=args.summary, budget=args.budget, ledger_snapshot=args.ledger_snapshot,
        export_manifest=args.export_manifest, reproduction=args.reproduction, extra=args.extra)
    data = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    output = args.output if args.output.is_absolute() else ROOT / args.output
    require(output.resolve().is_relative_to(ROOT) and not output.is_symlink(), "Index output must remain in project")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        require(output.read_bytes() == data, "Refusing to overwrite a different integrity index")
    else:
        with output.open("xb") as stream:
            stream.write(data)
    print(json.dumps({"output": str(output), "sha256": sha(data), "artifacts": len(result["artifacts"]),
                      "model_calls": 0, "kernel_calls": 0, "scientific_validity": "not_assessed", "E0": "not_passed"}))


if __name__ == "__main__":
    main()
