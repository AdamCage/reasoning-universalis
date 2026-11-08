"""Lossless delta archive for one closed pilot-v2 namespace, without model calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
FORMAT = "reasoning-universalis-pilot-v2-delta-v1"
MAX_ARCHIVE = 95 * 1024 * 1024
HEX = re.compile(r"^[0-9a-f]{64}$")
CALL_NAMES = {"request.json", "reservation.json", "response.json", "result.json", "trace.json"}


class DeltaError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DeltaError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(value):
    require(isinstance(value, str) and value and "\\" not in value and "\x00" not in value, "Unsafe delta path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value and all(p not in (".", "..") and ":" not in p for p in path.parts),
            "Unsafe delta path")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {"COM" + str(i) for i in range(1, 10)} | {"LPT" + str(i) for i in range(1, 10)}
    require(all(not part.endswith((".", " ")) and not any(ord(character) < 32 for character in part)
                and part.split(".", 1)[0].upper() not in reserved for part in path.parts), "Unsafe Windows delta path")
    return path


def regular(path, root):
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), "Unsafe delta source file")
    for ancestor in path.parents:
        if ancestor == root:
            break
        require(not ancestor.is_symlink(), "Symlinked delta source ancestor")


def helper_module():
    path = Path(__file__).with_name("export_local_evidence.py")
    spec = importlib.util.spec_from_file_location("pilot_v2_export_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scan_json(value, guards, secrets):
    """Inspect encoded HTTP bodies even inside arbitrary namespace receipts."""
    if isinstance(value, dict):
        if "http_status" in value or "body_base64" in value:
            guards.check_json_privacy(value, secrets, http_wrapper=True)
        for member in value.values():
            scan_json(member, guards, secrets)
    elif isinstance(value, list):
        for member in value:
            scan_json(member, guards, secrets)


def namespace_allowed(relative, source_names):
    parts = PurePosixPath(relative).parts
    if len(parts) == 1:
        return relative in {"protocol.json", "corpus.json", "source-inventory.json", "ledger-launch.json",
                            "dispatch-plan.json", "results.json", "cost-plan.json", "route-state.json"}
    if parts[0] == "source":
        return PurePosixPath(*parts[1:]).as_posix() in source_names
    if len(parts) == 2 and parts[0] in {"intents", "cost-plans"}:
        return parts[-1].endswith(".json") and HEX.fullmatch(parts[-1][:-5]) is not None
    if len(parts) == 2 and parts[0] == "metadata":
        return parts[-1] in {"deepseek_deepseek-v4.1-flash-endpoints.json", "openai_gpt-oss-20b-endpoints.json"}
    return len(parts) == 3 and parts[:2] == ("metadata", "history") and parts[-1].endswith(".json") and HEX.fullmatch(parts[-1][:-5]) is not None


def export_delta(state, protocol_path, support_path, output, *, project=PROJECT, secrets=()):
    state, project = Path(state).resolve(strict=True), Path(project).resolve(strict=True)
    protocol_path, support_path, output = Path(protocol_path).resolve(strict=True), Path(support_path).resolve(strict=True), Path(output).absolute()
    require(not output.exists(), "Choose a new delta output directory")
    require(not output.resolve().is_relative_to(state) and not state.is_relative_to(output.resolve()), "Delta output overlaps live state")
    protocol_bytes = protocol_path.read_bytes()
    protocol = json.loads(protocol_bytes)
    require(protocol.get("status") == "prospective_frozen_development_probe", "Only the finalized development protocol can be exported")
    protocol_hash = sha(protocol_bytes)
    scope = state / "pilot-v2" / protocol_hash
    for name in ("protocol.json", "corpus.json", "source-inventory.json", "ledger-launch.json", "dispatch-plan.json", "results.json"):
        require((scope / name).is_file(), "Pilot-v2 results/binding are incomplete: " + name)
    require((scope / "protocol.json").read_bytes() == protocol_bytes, "Pilot-v2 protocol snapshot differs")
    source_inventory = json.loads((scope / "source-inventory.json").read_bytes())
    plan, results = (json.loads((scope / name).read_bytes()) for name in ("dispatch-plan.json", "results.json"))
    require(len(plan["cells"]) == 192 and len(results["records"]) == 192, "Delta requires the full planned-cell registry")
    planned = {cell["call_id"]: cell for cell in plan["cells"]}
    parents = {row["parent_admission_call_id"] for row in protocol["models"]}
    require(len(planned) == 192 and len(parents) == 2 and all(HEX.fullmatch(k) for k in set(planned) | parents), "Invalid delta call roster")
    files = {}
    for name in ("ledger.json", "protocol.json", "corpus.json", "source-inventory.json", "dispatch-window.json"):
        files["state/" + name] = state / name
    for path in sorted(scope.rglob("*")):
        if path.is_file() and path.suffix in (".json", ".py"):
            require(namespace_allowed(path.relative_to(scope).as_posix(), source_inventory["files"]),
                    "Unprescribed JSON/Python file in pilot-v2 namespace")
            files["state/" + path.relative_to(state).as_posix()] = path
    for call_id in sorted(set(planned) | parents):
        directory = state / "calls" / call_id
        for name in sorted(CALL_NAMES):
            path = directory / name
            if path.is_file():
                files["state/calls/" + call_id + "/" + name] = path
    files["project/design/PILOT_V2_PROTOCOL_2026_11_08.json"] = protocol_path
    corpus_path = project / safe_relative(protocol["tasks"]["path"])
    require(corpus_path.read_bytes() == (scope / "corpus.json").read_bytes(), "Public and bound pilot-v2 corpus differ")
    files["project/" + protocol["tasks"]["path"]] = corpus_path
    files["project/artifacts/pilot-v2-2026-11-08/class-support.json"] = support_path
    for section in ("statistical_plan", "planning_scenarios"):
        if section in protocol:
            relative = protocol[section]["path"]
            safe_relative(relative)
            path = project / relative
            require(sha(path.read_bytes()) == protocol[section]["sha256"], "Prospectively bound public design artifact changed")
            files["project/" + relative] = path
    # Use actual frozen bytes, including inherited CRLF sources. Git LF blobs
    # are not substituted for execution snapshots.
    for name, digest in source_inventory["files"].items():
        safe_relative(name)
        path = scope / "source" / name
        require(path.is_file() and sha(path.read_bytes()) == digest, "Frozen delta source is absent or changed")
        files["project/" + name] = path
    for name in ("requirements-resumption.txt", "scripts/export_pilot_v2.py", "scripts/reproduce_pilot_v2.py",
                 "scripts/export_local_evidence.py", "scripts/summarize_pilot_v2.py",
                 "scripts/build_pilot_v2_evidence_index.py", "design/PILOT_V2_PROVIDER_RECOVERY_DECISION.json"):
        path = project / name
        if path.is_file():
            files["project/" + name] = path
    artifact_dir = project / "artifacts/pilot-v2-2026-11-08"
    if artifact_dir.exists():
        for path in sorted(artifact_dir.rglob("*")):
            if path.is_file() and path.suffix in (".json", ".md", ".csv", ".tsv", ".txt", ".png", ".pdf", ".svg"):
                files.setdefault("project/" + path.relative_to(project).as_posix(), path)
    for path in sorted((project / "reports").glob("*PILOT_V2*.md")):
        files["project/" + path.relative_to(project).as_posix()] = path
    for name, path in files.items():
        safe_relative(name)
        regular(path, state if name.startswith("state/") else project if path.is_relative_to(project) else state)
    before = {name: (path.stat().st_size, path.stat().st_mtime_ns) for name, path in files.items()}
    guards = helper_module()
    rows = []
    for name, path in sorted(files.items()):
        data = path.read_bytes()
        guards.scan(data, secrets)
        if name.endswith(".json"):
            scan_json(json.loads(data), guards, secrets)
        if name.startswith("state/calls/") and name.endswith("/response.json"):
            guards.check_json_privacy(json.loads(data), secrets, http_wrapper=True)
        elif name.startswith("state/calls/") and name.endswith("/result.json"):
            guards.check_json_privacy(json.loads(data).get("response"), secrets, http_wrapper=True)
        elif "/metadata/" in name and name.endswith(".json"):
            guards.check_json_privacy(json.loads(data).get("response"), secrets, http_wrapper=True)
        rows.append({"path": name, "sha256": sha(data), "bytes": len(data)})
    registry = {"schema_version": 1, "planned_call_ids": list(planned), "parent_admission_call_ids": sorted(parents),
                "cells": [{"call_id": call_id, "condition_id": cell["condition_id"],
                           "retained_files": sorted(name for name in CALL_NAMES if (state / "calls" / call_id / name).is_file()),
                           "intent_retained": (scope / "intents" / (call_id + ".json")).is_file()}
                          for call_id, cell in planned.items()]}
    registry_bytes = encoded(registry)
    guards.scan(registry_bytes, secrets)
    rows.append({"path": "bundle/attempt-registry.json", "sha256": sha(registry_bytes), "bytes": len(registry_bytes)})
    payload = {"schema_version": 1, "format": FORMAT, "created_utc": datetime.now(timezone.utc).isoformat(),
               "protocol_sha256": protocol_hash, "source_inventory_sha256": sha((scope / "source-inventory.json").read_bytes()),
               "v1_bundle_manifest_sha256": protocol["parent"]["v1_raw_bundle_manifest_sha256"],
               "scope": "lossless pilot-v2 delta; original v1 raw bundle remains separate and unchanged",
               "shared_ledger_path": "state/ledger.json", "namespace": "state/pilot-v2/" + protocol_hash,
               "files": rows, "scientific_validity": "not_assessed", "E0": "not_passed"}
    payload_bytes = encoded(payload)
    guards.scan(payload_bytes, secrets)
    output.mkdir(parents=True)
    archive_path = output / "evidence.zip"
    with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for row in rows:
            data = registry_bytes if row["path"] == "bundle/attempt-registry.json" else files[row["path"]].read_bytes()
            require(sha(data) == row["sha256"] and len(data) == row["bytes"], "Delta source changed during compression")
            info = zipfile.ZipInfo(row["path"], date_time=(2026, 11, 8, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, data)
        archive.writestr("manifest.json", payload_bytes)
    require(archive_path.stat().st_size < MAX_ARCHIVE, "Delta ZIP exceeds the 95 MiB publication limit; shard before publication")
    require(before == {name: (path.stat().st_size, path.stat().st_mtime_ns) for name, path in files.items()},
            "Delta snapshot changed during export")
    manifest = {"schema_version": 1, "format": FORMAT, "payload": payload, "payload_sha256": sha(payload_bytes),
                "archive": {"path": "evidence.zip", "sha256": sha(archive_path.read_bytes()), "bytes": archive_path.stat().st_size}}
    manifest_path = output / "manifest.json"
    manifest_path.write_bytes(encoded(manifest))
    result = verify_delta(manifest_path)
    result.update(manifest=str(manifest_path), manifest_sha256=sha(manifest_path.read_bytes()))
    return result


def verify_delta(manifest_path, unpack=None):
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(manifest_path.read_bytes())
    require(manifest.get("schema_version") == 1 and manifest.get("format") == FORMAT, "Unknown delta manifest format")
    payload = manifest["payload"]
    payload_bytes = encoded(payload)
    require(sha(payload_bytes) == manifest["payload_sha256"] and payload.get("format") == FORMAT
            and payload.get("scientific_validity") == "not_assessed", "Delta payload manifest hash/status mismatch")
    archive_info = manifest["archive"]
    require(archive_info.get("path") == "evidence.zip", "Unsafe delta archive name")
    archive_path = manifest_path.parent / "evidence.zip"
    regular(archive_path, manifest_path.parent)
    raw = archive_path.read_bytes()
    require(len(raw) == archive_info["bytes"] < MAX_ARCHIVE and sha(raw) == archive_info["sha256"], "Delta ZIP hash/size mismatch")
    rows = payload["files"]
    names = [row["path"] for row in rows]
    require(len(names) == len(set(name.casefold() for name in names)) and "manifest.json" not in names, "Duplicate delta payload path")
    for name in names:
        safe_relative(name)
        require(name.startswith(("state/", "project/", "bundle/")), "Unsupported delta path prefix")
    destination = Path(unpack).absolute() if unpack is not None else None
    require(destination is None or not destination.exists(), "Delta unpack destination already exists")
    with zipfile.ZipFile(archive_path) as archive:
        require(len(archive.infolist()) == len(rows) + 1 and set(archive.namelist()) == set(names) | {"manifest.json"},
                "Delta ZIP member roster mismatch")
        require(archive.read("manifest.json") == payload_bytes, "Internal and external delta manifests differ")
        for row in rows:
            data = archive.read(row["path"])
            require(len(data) == row["bytes"] and sha(data) == row["sha256"], "Delta member hash/size mismatch")
        if destination is not None:
            destination.mkdir(parents=True)
            for row in rows:
                path = destination / Path(*PurePosixPath(row["path"]).parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(row["path"]))
            (destination / "delta-manifest.json").write_bytes(manifest_path.read_bytes())
    return {"verified": True, "files": len(rows), "archive_sha256": archive_info["sha256"],
            "archive_bytes": archive_info["bytes"], "unpacked": destination is not None,
            "protocol_sha256": payload["protocol_sha256"], "scientific_validity": "not_assessed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--export", type=Path, metavar="STATE")
    commands.add_argument("--verify", type=Path, metavar="MANIFEST")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--support", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--unpack", type=Path)
    parser.add_argument("--env-file", type=Path, default=PROJECT / ".env")
    args = parser.parse_args()
    if args.export and (not args.protocol or not args.support or not args.output or args.unpack):
        parser.error("--export needs --protocol --support --output, without --unpack")
    try:
        result = (export_delta(args.export, args.protocol, args.support, args.output,
                               secrets=helper_module().credentials(args.env_file)) if args.export
                  else verify_delta(args.verify, args.unpack))
    except (DeltaError, OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({"failed": True, "reason": str(exc) if isinstance(exc, DeltaError) else type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
