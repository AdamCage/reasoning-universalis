"""Lossless R1 delta with the separately sealed primary-A bundle embedded."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
FORMAT = "reasoning-universalis-pilot-v2-recovery-delta-v1"
STATUS = "prospective_frozen_provider_recovery"
SUPPORT = "artifacts/pilot-v2-recovery-2026-11-08/class-support.json"
PROTOCOL = "design/PILOT_V2_PROVIDER_RECOVERY_PROTOCOL.json"


def sibling(name):
    spec = importlib.util.spec_from_file_location("recovery_" + name, Path(__file__).with_name(name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


A = sibling("export_pilot_v2")
require, encoded, sha, safe_relative = A.require, A.encoded, A.sha, A.safe_relative


def namespace_allowed(relative, source_names):
    return relative == "reuse-mapping.json" or A.namespace_allowed(relative, source_names)


def verify_nested_parent(manifest_bytes, archive_bytes, expected_hash):
    require(sha(manifest_bytes) == expected_hash, "Sealed primary-A manifest hash differs")
    with tempfile.TemporaryDirectory(prefix="pilot-v2-parent-check-") as temporary:
        root = Path(temporary)
        (root / "manifest.json").write_bytes(manifest_bytes)
        (root / "evidence.zip").write_bytes(archive_bytes)
        return A.verify_delta(root / "manifest.json")


def export_recovery(state, protocol_path, support_path, parent_manifest, output, *, project=PROJECT, secrets=()):
    state, project = Path(state).resolve(strict=True), Path(project).resolve(strict=True)
    protocol_path, support_path = Path(protocol_path).resolve(strict=True), Path(support_path).resolve(strict=True)
    parent_manifest, output = Path(parent_manifest).resolve(strict=True), Path(output).absolute()
    require(not output.exists(), "Choose a new R1 delta output directory")
    require(not output.resolve().is_relative_to(state) and not state.is_relative_to(output.resolve()), "R1 output overlaps live state")
    protocol_bytes = protocol_path.read_bytes()
    protocol = json.loads(protocol_bytes)
    recovery = protocol["recovery"]
    require(protocol.get("status") == STATUS and recovery["condition"] == "R1", "Only the finalized R1 condition can be exported")
    protocol_hash = sha(protocol_bytes)
    scope = state / "pilot-v2-recovery" / protocol_hash
    inventory = json.loads((scope / "source-inventory.json").read_bytes())
    plan, results = (json.loads((scope / name).read_bytes()) for name in ("dispatch-plan.json", "results.json"))
    require((scope / "protocol.json").read_bytes() == protocol_bytes, "Bound R1 protocol differs")
    require(len(plan["cells"]) == len(results["records"]) == 192, "R1 delta requires all 192 planned rows")
    new = [cell for cell in plan["cells"] if cell["model"] == "openai/gpt-oss-20b"]
    require(len(new) == len({cell["call_id"] for cell in new}) == 96, "R1 must retain the fixed new96 roster")
    parent_raw = parent_manifest.read_bytes()
    parent_hash = sha(parent_raw)
    require(parent_hash == recovery["parent_delta_manifest_sha256"], "R1 protocol does not bind this sealed primary-A bundle")
    parent_archive = parent_manifest.parent / "evidence.zip"
    A.verify_delta(parent_manifest)
    files = {"bundle/parent-A/manifest.json": parent_manifest, "bundle/parent-A/evidence.zip": parent_archive,
             "state/ledger.json": state / "ledger.json",
             "state/pilot-v2-recovery/condition-R1.json": state / "pilot-v2-recovery/condition-R1.json",
             "project/" + PROTOCOL: protocol_path, "project/" + SUPPORT: support_path}
    for path in sorted(scope.rglob("*")):
        if path.is_file() and path.suffix in (".json", ".py"):
            require(namespace_allowed(path.relative_to(scope).as_posix(), inventory["files"]), "Unprescribed R1 namespace file")
            files["state/" + path.relative_to(state).as_posix()] = path
    for name, digest in inventory["files"].items():
        safe_relative(name)
        path = scope / "source" / name
        require(sha(path.read_bytes()) == digest, "Frozen R1 source changed")
        files["project/" + name] = path
    decision_path = project / safe_relative(recovery["decision_path"])
    require(sha(decision_path.read_bytes()) == recovery["decision_sha256"], "Prospective R1 decision changed")
    files["project/" + recovery["decision_path"]] = decision_path
    corpus = project / safe_relative(protocol["tasks"]["path"])
    require(corpus.read_bytes() == (scope / "corpus.json").read_bytes(), "Public R1 corpus differs")
    files["project/" + protocol["tasks"]["path"]] = corpus
    parents = {row["parent_admission_call_id"] for row in protocol["models"] if row["model"] == "openai/gpt-oss-20b"}
    for call_id in sorted({cell["call_id"] for cell in new} | parents):
        require(A.HEX.fullmatch(call_id), "Unsafe R1 call ID")
        for name in A.CALL_NAMES:
            path = state / "calls" / call_id / name
            if path.is_file():
                files["state/calls/" + call_id + "/" + name] = path
    for section in ("statistical_plan", "planning_scenarios"):
        if section in protocol:
            item = protocol[section]
            path = project / safe_relative(item["path"])
            require(sha(path.read_bytes()) == item["sha256"], "Bound R1 design artifact differs")
            files["project/" + item["path"]] = path
    for name in ("requirements-resumption.txt", "scripts/export_pilot_v2_recovery.py",
                 "scripts/reproduce_pilot_v2_recovery.py", "scripts/export_pilot_v2.py",
                 "scripts/reproduce_pilot_v2.py", "scripts/export_local_evidence.py",
                 "scripts/summarize_pilot_v2_recovery.py", "scripts/summarize_pilot_v2.py"):
        path = project / name
        if path.is_file():
            files["project/" + name] = path
    artifact_dir = project / "artifacts/pilot-v2-recovery-2026-11-08"
    if artifact_dir.is_dir():
        for path in sorted(artifact_dir.rglob("*")):
            if path.is_file() and path.suffix in (".json", ".md", ".csv", ".tsv", ".txt", ".png", ".svg", ".pdf"):
                files.setdefault("project/" + path.relative_to(project).as_posix(), path)
    for path in sorted((project / "reports").glob("*PILOT_V2*RECOVERY*.md")):
        files["project/" + path.relative_to(project).as_posix()] = path
    guards = A.helper_module()
    rows, signatures = [], {}
    for name, path in sorted(files.items()):
        safe_relative(name)
        root = project if path.is_relative_to(project) else state if path.is_relative_to(state) else parent_manifest.parent
        A.regular(path, root)
        signatures[name] = path.stat().st_size, path.stat().st_mtime_ns
        data = path.read_bytes()
        guards.scan(data, secrets)
        if name.endswith(".json"):
            A.scan_json(json.loads(data), guards, secrets)
        rows.append({"path": name, "sha256": sha(data), "bytes": len(data)})
    # A was scanned at its seal; rescan all original uncompressed bytes against
    # the currently configured credential as well. Never scan only ZIP bytes.
    with zipfile.ZipFile(parent_archive) as archive:
        for name in archive.namelist():
            data = archive.read(name)
            guards.scan(data, secrets)
            if name.endswith(".json"):
                A.scan_json(json.loads(data), guards, secrets)
    payload = {"schema_version": 1, "format": FORMAT, "condition": "R1",
               "created_utc": datetime.now(timezone.utc).isoformat(), "protocol_sha256": protocol_hash,
               "namespace": "state/pilot-v2-recovery/" + protocol_hash,
               "source_inventory_sha256": sha((scope / "source-inventory.json").read_bytes()),
               "primary_A_manifest_sha256": parent_hash,
               "v1_bundle_manifest_sha256": protocol["parent"]["v1_raw_bundle_manifest_sha256"],
               "files": rows, "scientific_validity": "not_assessed", "E0": "not_passed",
               "scope": "R1 supplement with exact sealed primary A; original A remains unchanged"}
    payload_bytes = encoded(payload)
    guards.scan(payload_bytes, secrets)
    output.mkdir(parents=True)
    archive_path = output / "evidence.zip"
    with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for row in rows:
            data = files[row["path"]].read_bytes()
            require(sha(data) == row["sha256"] and len(data) == row["bytes"], "R1 source changed during compression")
            info = zipfile.ZipInfo(row["path"], (2026, 11, 8, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, data)
        archive.writestr("manifest.json", payload_bytes)
    require(archive_path.stat().st_size < A.MAX_ARCHIVE, "R1 ZIP exceeds the 95 MiB publication limit")
    require(signatures == {name: (path.stat().st_size, path.stat().st_mtime_ns) for name, path in files.items()},
            "R1 snapshot changed during export")
    manifest = {"schema_version": 1, "format": FORMAT, "payload": payload, "payload_sha256": sha(payload_bytes),
                "archive": {"path": "evidence.zip", "bytes": archive_path.stat().st_size, "sha256": sha(archive_path.read_bytes())}}
    manifest_path = output / "manifest.json"
    manifest_path.write_bytes(encoded(manifest))
    return {**verify_recovery(manifest_path), "manifest_sha256": sha(manifest_path.read_bytes())}


def verify_recovery(manifest_path, unpack=None):
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(manifest_path.read_bytes())
    payload, archive_info = manifest["payload"], manifest["archive"]
    require(manifest.get("format") == payload.get("format") == FORMAT and manifest.get("schema_version") == 1
            and payload.get("condition") == "R1" and payload.get("scientific_validity") == "not_assessed", "Unknown R1 delta format/status")
    payload_bytes = encoded(payload)
    require(sha(payload_bytes) == manifest["payload_sha256"], "R1 payload manifest hash differs")
    require(archive_info["path"] == "evidence.zip", "Unsafe R1 archive filename")
    archive_path = manifest_path.parent / "evidence.zip"
    A.regular(archive_path, manifest_path.parent)
    raw = archive_path.read_bytes()
    require(len(raw) == archive_info["bytes"] < A.MAX_ARCHIVE and sha(raw) == archive_info["sha256"], "R1 ZIP hash/size differs")
    rows = payload["files"]
    names = [row["path"] for row in rows]
    require(len(names) == len({name.casefold() for name in names}) and "manifest.json" not in names, "Repeated R1 payload path")
    for name in names:
        safe_relative(name)
        require(name.startswith(("state/", "project/", "bundle/")), "Unsupported R1 payload path")
    destination = Path(unpack).absolute() if unpack is not None else None
    require(destination is None or not destination.exists(), "R1 unpack destination exists")
    with zipfile.ZipFile(archive_path) as archive:
        require(len(archive.infolist()) == len(rows) + 1 and set(archive.namelist()) == set(names) | {"manifest.json"},
                "R1 member roster differs")
        require(archive.read("manifest.json") == payload_bytes, "Internal R1 manifest differs")
        for row in rows:
            data = archive.read(row["path"])
            require(len(data) == row["bytes"] and sha(data) == row["sha256"], "R1 member hash/size differs")
        verify_nested_parent(archive.read("bundle/parent-A/manifest.json"), archive.read("bundle/parent-A/evidence.zip"),
                             payload["primary_A_manifest_sha256"])
        if destination is not None:
            destination.mkdir(parents=True)
            for row in rows:
                path = destination / safe_relative(row["path"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(row["path"]))
            (destination / "delta-manifest.json").write_bytes(manifest_path.read_bytes())
    return {"verified": True, "files": len(rows), "archive_sha256": archive_info["sha256"], "archive_bytes": archive_info["bytes"],
            "protocol_sha256": payload["protocol_sha256"], "primary_A_manifest_sha256": payload["primary_A_manifest_sha256"],
            "unpacked": destination is not None, "scientific_validity": "not_assessed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--export", type=Path, metavar="STATE")
    commands.add_argument("--verify", type=Path, metavar="MANIFEST")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--support", type=Path)
    parser.add_argument("--parent-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--unpack", type=Path)
    parser.add_argument("--env-file", type=Path, default=PROJECT / ".env")
    args = parser.parse_args()
    if args.export and (not args.protocol or not args.support or not args.parent_manifest or not args.output or args.unpack):
        parser.error("--export needs --protocol --support --parent-manifest --output")
    try:
        result = (export_recovery(args.export, args.protocol, args.support, args.parent_manifest, args.output,
                                  secrets=A.helper_module().credentials(args.env_file)) if args.export
                  else verify_recovery(args.verify, args.unpack))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({"failed": True, "reason": str(exc) if isinstance(exc, A.DeltaError) else type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
