"""Lossless closed machine-annotation delta with the sealed R1 parent included."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "reasoning-universalis-machine-development-delta-v1"


def sibling(name):
    spec = importlib.util.spec_from_file_location("machine_export_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARENT = sibling("export_pilot_v2_recovery")
A = PARENT.A
require, sha, encoded, safe = A.require, A.sha, A.encoded, A.safe_relative
RUNTIME_SUPPORT = ("stage0/__init__.py", "stage0/tasks.py", "stage2/__init__.py", "measurement/__init__.py")
PROGRAMS = ("scripts/summarize_machine_development.py", "scripts/export_machine_development.py", "scripts/reproduce_machine_development.py",
            "scripts/export_pilot_v2_recovery.py", "scripts/reproduce_pilot_v2_recovery.py", "scripts/export_pilot_v2.py",
            "scripts/reproduce_pilot_v2.py", "scripts/export_local_evidence.py")


def source_allowed(relative, inventory):
    if relative.startswith("source/"):
        return relative[len("source/"):] in inventory
    if relative in {"protocol.json", "items.json", "codebook.json", "mapping.json", "annotation_config.json", "route_metadata.json",
                    "license_receipt.json", "source-inventory.json", "ledger-launch.json", "dispatch-plan.json", "dispatch-window.json",
                    "cost-plan.json", "route-state.json", "results.json"}:
        return True
    parts = relative.split("/")
    if len(parts) == 2 and parts[0] in ("intents", "votes", "cost-plans"):
        return parts[1].endswith(".json") and bool(A.HEX.fullmatch(parts[1][:-5]))
    if len(parts) == 3 and parts[:2] == ["metadata", "history"]:
        return parts[2].endswith(".json") and bool(A.HEX.fullmatch(parts[2][:-5]))
    return len(parts) == 2 and parts[0] == "metadata" and parts[1] == "deepseek_deepseek-v4.1-flash-endpoints.json"


def export(state, protocol_path, parent_manifest, output, *, project=ROOT, secrets=()):
    state, project, protocol_path = map(lambda value: Path(value).resolve(strict=True), (state, project, protocol_path))
    output, parent_manifest = Path(output).absolute(), Path(parent_manifest).resolve(strict=True)
    require(not output.exists() and not output.resolve().is_relative_to(state) and not state.is_relative_to(output.resolve()),
            "Choose a new machine archive directory outside live state")
    p_raw, p = protocol_path.read_bytes(), json.loads(protocol_path.read_bytes())
    digest = sha(p_raw)
    scope = state / "machine-development" / digest
    result, plan, inventory = (json.loads((scope / name).read_bytes()) for name in ("results.json", "dispatch-plan.json", "source-inventory.json"))
    require(p["status"] == "prospective_frozen_machine_development" and p_raw == (scope / "protocol.json").read_bytes()
            and result["protocol_sha256"] == digest and result["maximum_calls"] == len(result["all_planned_calls"]) == len(plan["cells"]),
            "Export only a closed all-planned-cell machine condition")
    PARENT.verify_recovery(parent_manifest)
    parent_raw = parent_manifest.read_bytes()
    require(sha(parent_raw) == p["parent"].get("machine_parent_R1_manifest_sha256", sha(parent_raw)),
            "The declared sealed R1 parent differs")
    files = {"bundle/parent-R1/manifest.json": parent_manifest, "bundle/parent-R1/evidence.zip": parent_manifest.parent / "evidence.zip",
             "state/ledger.json": state / "ledger.json", "state/protocol.json": state / "protocol.json",
             "state/source-inventory.json": state / "source-inventory.json"}
    condition = state / "machine-development/condition-v1.json"
    if condition.is_file():
        files["state/machine-development/condition-v1.json"] = condition
    else:
        require(len(json.loads((state / "ledger.json").read_bytes())) == p["parent"]["launch_ledger_rows"],
                "A paid machine condition lost its registry")
    for path in sorted(scope.rglob("*")):
        if path.is_file():
            require(source_allowed(path.relative_to(scope).as_posix(), inventory["files"]), "Unexpected file in machine namespace")
            files["state/" + path.relative_to(state).as_posix()] = path
    for name, expected in inventory["files"].items():
        safe(name)
        path = scope / "source" / name
        require(sha(path.read_bytes()) == expected, "Frozen machine source changed")
        files["project/" + name] = path
    for spec in [p["inputs"], p["inputs"]["codebook"], p["inputs"]["mapping"], p["annotation_config"]]:
        path = project / safe(spec["path"])
        require(sha(path.read_bytes()) == spec["file_sha256"], "Public machine input changed")
        files["project/" + spec["path"]] = path
    relative_protocol = protocol_path.relative_to(project).as_posix()
    files["project/" + relative_protocol] = protocol_path
    call_ids = {cell["call_id"] for cell in plan["cells"]}
    require(all(path.stem in call_ids for path in (scope / "intents").glob("*.json")), "Unmapped machine intent")
    for directory in (state / "calls").iterdir():
        context_path = directory / "reservation.json"
        if context_path.is_file():
            context = json.loads(context_path.read_bytes())
            require(context.get("protocol_sha256") != digest or directory.name in call_ids,
                    "Unmapped physical attempt under the current machine condition")
    for call_id in sorted(call_ids | {p["parent"]["admission_call_id"]}):
        require(A.HEX.fullmatch(call_id), "Unsafe physical call ID")
        for name in A.CALL_NAMES:
            path = state / "calls" / call_id / name
            if path.is_file():
                files["state/calls/" + call_id + "/" + name] = path
    for name in (*PROGRAMS, *RUNTIME_SUPPORT, "requirements-resumption.txt"):
        path = project / name
        require(path.is_file(), "Offline replay dependency is missing: " + name)
        files.setdefault("project/" + name, path)
    diagnostic_program = project / "scripts/audit_machine_vote_failures.py"
    if diagnostic_program.is_file():
        files["project/scripts/audit_machine_vote_failures.py"] = diagnostic_program
    artifact = project / Path(p["inputs"]["path"]).parent
    require(all((artifact / name).is_file() for name in ("results.json", "summary.json", "budget-final.json"))
            and (artifact / "results.json").read_bytes() == (scope / "results.json").read_bytes(),
            "Build the closed strict machine summary before exporting final evidence")
    for path in sorted(artifact.iterdir()):
        if path.is_file() and path.suffix in (".json", ".md", ".csv", ".txt"):
            files.setdefault("project/" + path.relative_to(project).as_posix(), path)
    mapping = json.loads((project / p["inputs"]["mapping"]["path"]).read_bytes())
    source = mapping.get("source")
    if source:
        package = project / safe(source["path"])
        manifest_path = package / "coordinator/package-manifest.json"
        require(sha(manifest_path.read_bytes()) == source["manifest_sha256"], "Original S2 source package changed")
        package_manifest = json.loads(manifest_path.read_bytes())
        for row in package_manifest["files"] + [{"path": "coordinator/package-manifest.json", "sha256": source["manifest_sha256"]}]:
            path = package / safe(row["path"])
            require(sha(path.read_bytes()) == row["sha256"], "Original S2 source proof changed")
            files["project/" + path.relative_to(project).as_posix()] = path
    reports = set((project / "reports").glob("*MACHINE*DEVELOPMENT*.md")) | set((project / "reports").glob("MACHINE_VOTE_FAILURE_AUDIT.md"))
    for path in sorted(reports):
        files["project/" + path.relative_to(project).as_posix()] = path
    guards, rows = A.helper_module(), []
    for name, path in sorted(files.items()):
        safe(name)
        base = project if path.is_relative_to(project) else parent_manifest.parent
        A.regular(path, base)
        data = path.read_bytes()
        guards.scan(data, secrets)
        if name.endswith(".json"):
            A.scan_json(json.loads(data), guards, secrets)
        rows.append({"path": name, "bytes": len(data), "sha256": sha(data)})
    # Nested old archives are immutable; still scan their expanded public bytes.
    with zipfile.ZipFile(parent_manifest.parent / "evidence.zip") as archive:
        for name in archive.namelist():
            guards.scan(archive.read(name), secrets)
    payload = {"schema_version": 1, "format": FORMAT, "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": digest, "protocol_path": relative_protocol, "namespace": "state/machine-development/" + digest,
        "source_inventory_sha256": sha((scope / "source-inventory.json").read_bytes()),
        "parent_R1_manifest_sha256": sha(parent_raw), "files": rows,
        "offline_import_support_not_measured_source_closure": [name for name in RUNTIME_SUPPORT if name not in inventory["files"]],
        "scope": "machine-only development labels; original E0 source packet remains empty human preparation",
        "scientific_validity": "not_assessed", "E0": "not_passed", "human_gold": "not_created"}
    payload_raw = encoded(payload)
    output.mkdir(parents=True)
    archive_path = output / "evidence.zip"
    with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for row in rows:
            data = files[row["path"]].read_bytes()
            require(len(data) == row["bytes"] and sha(data) == row["sha256"], "Machine export input changed during compression")
            info = zipfile.ZipInfo(row["path"], (2026, 11, 8, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, data)
        archive.writestr("manifest.json", payload_raw)
    require(archive_path.stat().st_size < A.MAX_ARCHIVE, "Machine evidence exceeds the95 MiB publication bound")
    manifest = {"schema_version": 1, "format": FORMAT, "payload": payload, "payload_sha256": sha(payload_raw),
        "archive": {"path": "evidence.zip", "bytes": archive_path.stat().st_size, "sha256": sha(archive_path.read_bytes())}}
    manifest_path = output / "manifest.json"
    manifest_path.write_bytes(encoded(manifest))
    return verify(manifest_path)


def verify(manifest_path, unpack=None):
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(manifest_path.read_bytes())
    payload = manifest["payload"]
    require(manifest["format"] == payload["format"] == FORMAT and manifest["schema_version"] == 1, "Unknown machine evidence format")
    payload_raw = encoded(payload)
    require(sha(payload_raw) == manifest["payload_sha256"] and payload["E0"] == "not_passed"
            and payload["human_gold"] == "not_created" and manifest["archive"]["path"] == "evidence.zip", "Machine manifest identity or claim changed")
    archive_path = manifest_path.parent / "evidence.zip"
    A.regular(archive_path, manifest_path.parent)
    raw = archive_path.read_bytes()
    require(len(raw) == manifest["archive"]["bytes"] < A.MAX_ARCHIVE and sha(raw) == manifest["archive"]["sha256"], "Machine ZIP bytes differ")
    rows = payload["files"]
    names = [row["path"] for row in rows]
    require(len(names) == len({name.casefold() for name in names}) and "manifest.json" not in names, "Repeated machine archive member")
    for name in names:
        safe(name)
        require(name.startswith(("state/", "project/", "bundle/")), "Unexpected machine evidence path")
    destination = Path(unpack).absolute() if unpack is not None else None
    require(destination is None or not destination.exists(), "Choose a new machine unpack directory")
    with zipfile.ZipFile(archive_path) as archive:
        require(len(archive.infolist()) == len(rows) + 1 and set(archive.namelist()) == set(names) | {"manifest.json"}
                and archive.read("manifest.json") == payload_raw, "Machine ZIP roster differs")
        for row in rows:
            value = archive.read(row["path"])
            require(len(value) == row["bytes"] and sha(value) == row["sha256"], "Machine member bytes differ")
        with tempfile.TemporaryDirectory(prefix="machine-parent-check-") as temporary:
            parent = Path(temporary)
            parent_raw = archive.read("bundle/parent-R1/manifest.json")
            require(sha(parent_raw) == payload["parent_R1_manifest_sha256"], "Sealed R1 parent manifest differs")
            (parent / "manifest.json").write_bytes(parent_raw)
            (parent / "evidence.zip").write_bytes(archive.read("bundle/parent-R1/evidence.zip"))
            PARENT.verify_recovery(parent / "manifest.json")
        if destination is not None:
            destination.mkdir(parents=True)
            for row in rows:
                path = destination / safe(row["path"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(row["path"]))
            (destination / "delta-manifest.json").write_bytes(manifest_path.read_bytes())
    return {"verified": True, "files": len(rows), "archive_bytes": len(raw), "archive_sha256": sha(raw),
            "protocol_sha256": payload["protocol_sha256"], "E0": "not_passed", "scientific_validity": "not_assessed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--export", type=Path)
    commands.add_argument("--verify", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--parent-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--unpack", type=Path)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.export and (not args.protocol or not args.parent_manifest or not args.output):
        parser.error("--export requires --protocol --parent-manifest --output")
    secrets = A.helper_module().credentials(args.env_file) if args.env_file else ()
    result = export(args.export, args.protocol, args.parent_manifest, args.output, secrets=secrets) if args.export else verify(args.verify, args.unpack)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
