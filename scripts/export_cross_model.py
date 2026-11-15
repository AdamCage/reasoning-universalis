"""Package the public cross-model pilot without credentials or live-state reads.

The default archive can represent an offline preparation or actual attempted
annotations. Missing calls and invalid outputs remain explicit in its manifest.
Unpack the verified members into a fresh directory to recover project-relative
paths, then run scripts/reproduce_cross_model.py without an API key.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "reasoning-universalis-cross-model-evidence-v1"
ARTIFACT = "artifacts/cross-model-2026-11-15"
PROTOCOL = "design/CROSS_MODEL_PROTOCOL_2026_11_15.json"
EVIDENCE = "evidence/cross-model-2026-11-15"
COMPAT_ARTIFACT = "artifacts/cross-model-compat-2026-11-15"
COMPAT_PROTOCOL = "design/CROSS_MODEL_TRANSPORT_ADDENDUM_2026_11_15.json"
CONDITIONS = {"original": (ARTIFACT, PROTOCOL, EVIDENCE),
              "compat": (COMPAT_ARTIFACT, COMPAT_PROTOCOL, "evidence/cross-model-compat-2026-11-15")}
REPORT = "reports/CROSS_MODEL_MEASUREMENT_REPORT.md"
PDF = "output/pdf/cross-model-measurement-pilot.pdf"
REQUIRED = ("input-items.json", "mapping.json", "codebook.json", "source-inventory.json",
            "source-snapshot.zip", "parent-integrity.json", "ledger-launch.json", "cost-quote.json")
FORBIDDEN = {".env", ".research", ".git", "private", "secrets", "credentials"}
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"


def strict(data):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "Duplicate JSON object key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("Nonfinite JSON number: " + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def safe_relative(name):
    require(isinstance(name, str) and name and "\\" not in name and ":" not in name
            and not any(ord(c) < 32 for c in name), "Unsafe package path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and str(path) == name and all(p not in ("", ".", "..") for p in path.parts),
            "Unsafe package path")
    for part in path.parts:
        lowered = part.casefold()
        require(lowered not in FORBIDDEN and not lowered.startswith(".env.")
                and not part.endswith((" ", ".")), "Private or unsafe package path")
        stem = part.split(".", 1)[0].upper()
        require(stem not in {"CON", "PRN", "AUX", "NUL", *("COM" + str(i) for i in range(1, 10)),
                             *("LPT" + str(i) for i in range(1, 10))}, "Windows device package path")
    return path


def regular(project, name):
    relative = safe_relative(name)
    path = project.joinpath(*relative.parts)
    require(not path.is_symlink() and path.is_file() and path.resolve(strict=True).is_relative_to(project),
            "Missing, linked, or external public package input: " + name)
    # Parent-directory links must not smuggle other files into a public path.
    require(all(not p.is_symlink() for p in path.parents if p.is_relative_to(project)),
            "Linked public package input: " + name)
    return path


def _money(value):
    amount = Decimal(str(value))
    require(amount.is_finite() and amount >= 0, "Invalid packaged budget amount")
    return amount


def _run_state(files, protocol_raw, artifact=ARTIFACT):
    protocol = strict(protocol_raw)
    require(type(protocol) is dict, "Invalid protocol object")
    digest = sha(protocol_raw)
    allocation = protocol.get("allocation", {})
    planned = (allocation.get("remaining_full_context", 0) + allocation.get("remaining_without_context", 0)
               if artifact == COMPAT_ARTIFACT else allocation.get("maximum_calls", 194))
    require(type(planned) is int and planned >= 0, "Invalid planned-call denominator")
    annotation_name = artifact + "/new-annotations.json"
    annotations = strict(files[annotation_name]) if annotation_name in files else None
    cells = []
    if annotations is not None:
        require(type(annotations) is dict and annotations.get("protocol_sha256") == digest
                and type(annotations.get("cells")) is list, "Annotation protocol binding or cell list differs")
        cells = annotations["cells"]
    identities, statuses, raw_missing = set(), Counter(), {}
    for cell in cells:
        require(type(cell) is dict, "Invalid packaged annotation cell")
        identity = tuple(cell.get(k) for k in ("model", "condition", "item_id"))
        require(all(isinstance(v, str) and v for v in identity) and identity not in identities,
                "Repeated or missing packaged annotation identity")
        identities.add(identity)
        status = cell.get("technical_status")
        require(isinstance(status, str) and status, "Missing annotation technical status")
        statuses[status] += 1
        if "call_id" in cell:
            require(not status.startswith("not_dispatched"), "Unsent annotation cannot claim a physical call identity")
            call_id = cell["call_id"]
            require(len(safe_relative(call_id).parts) == 1, "Unsafe raw call identity")
            prefix = artifact + "/raw/" + call_id + "/"
            require(prefix + "request.json" in files, "Portable attempted request missing; run Collector.export() first")
            missing = [name for name in ("intent.json", "reservation.json", "response.json", "result.json") if prefix + name not in files]
            if missing:
                raw_missing[call_id] = missing
    require(len(cells) <= planned, "Recorded annotations exceed the frozen planned denominator")
    attempted = sum(n for status, n in statuses.items() if not status.startswith("not_dispatched"))
    study_attempted = sum(not c["technical_status"].startswith("not_dispatched")
                          and c.get("condition") != "schema_probe" for c in cells)
    probes_attempted = attempted - study_attempted
    quote_name = artifact + "/cost-quote.json"
    quoted = strict(files[quote_name])
    authorization_name = artifact + "/budget-authorization.json"
    authorized = authorization_name in files
    if authorized:
        auth = strict(files[authorization_name])
        require(auth.get("protocol_sha256") == digest and auth.get("quote_sha256") == sha(files[quote_name])
                and auth.get("explicit_user_confirmation") is True and bool(auth.get("user_instruction"))
                and str(auth.get("new_cap_rub")) == str(protocol.get("budget", {}).get("new_cap_rub", "400")),
                "Packaged budget authorization binding differs")
    launch = strict(files[artifact + "/ledger-launch.json"])
    require(type(launch) is list, "Invalid packaged launch ledger")
    launch_amount = sum((_money(row["charged_or_reserved_rub"]) for row in launch), Decimal(0))
    budget = {"authorization_state": "explicit_confirmation_recorded" if authorized else "pending_separate_confirmation",
              "new_cap_rub": str(protocol.get("budget", {}).get("new_cap_rub", "400")),
              "quoted_worst_case_reservation_rub": quoted.get("worst_case_reservation_rub"),
              "launch_rows": len(launch), "launch_charged_or_reserved_rub": str(launch_amount),
              "final_budget_artifact_present": artifact + "/budget-final.json" in files}
    final_name = artifact + "/budget-final.json"
    if final_name in files:
        budget["final"] = strict(files[final_name])
    analysis_name = artifact + "/analysis/summary.json"
    analysis = strict(files[analysis_name]) if analysis_name in files else {}
    return {"annotation_state": "measured" if study_attempted else "no_new_annotations",
            "collection_state": "study_attempted" if study_attempted else "technical_probes_only" if probes_attempted else "not_started",
            "annotation_artifact_present": annotations is not None, "planned_calls": planned,
            "recorded_cells": len(cells), "attempted_cells": attempted, "valid_annotations": statuses["valid"],
            "study_attempted_cells": study_attempted, "schema_probe_attempted_cells": probes_attempted,
            "study_valid_annotations": sum(c["technical_status"] == "valid" and c.get("condition") != "schema_probe" for c in cells),
            "technical_status_counts": dict(sorted(statuses.items())), "missing_planned_cells": planned - len(cells),
            "missing_raw_files": raw_missing, "analysis_state": analysis.get("status", "absent"),
            "budget": budget, "E0": "not_passed", "human_gold": "not_created",
            "scope": "Exploratory machine annotation instruments; no ground-truth or internal-state claim"}


def _condition_state(contents, condition):
    require(condition in CONDITIONS, "Unknown package condition")
    artifact, protocol_path, _ = CONDITIONS[condition]
    raw = contents[protocol_path]
    state = _run_state(contents, raw, artifact)
    if condition == "compat":
        protocol = strict(raw)
        require(protocol.get("parent_protocol") == PROTOCOL and PROTOCOL in contents
                and protocol.get("parent_protocol_sha256") == sha(contents[PROTOCOL]),
                "Compatibility parent protocol binding differs")
        parent_state = _run_state(contents, contents[PROTOCOL])
        state["parent_condition_state"] = parent_state
        state["total_attempted_cells_including_parent"] = state["attempted_cells"] + parent_state["attempted_cells"]
        state["authorized_total_calls"] = protocol.get("allocation", {}).get("maximum_total_calls", 194)
        require(state["total_attempted_cells_including_parent"] <= state["authorized_total_calls"],
                "Attempted calls exceed combined frozen authorization")
    return state


def _check_manifest(manifest, archive_path):
    require(type(manifest) is dict and manifest.get("format") == FORMAT and manifest.get("schema_version") == 1,
            "Unknown cross-model evidence format")
    payload = manifest.get("payload")
    require(type(payload) is dict and payload.get("format") == FORMAT
            and manifest.get("payload_sha256") == sha(encoded(payload)), "Payload manifest format or hash differs")
    reference = manifest.get("archive", {})
    require(reference.get("path") == "evidence.zip", "Unsafe archive reference")
    raw = archive_path.read_bytes()
    require(len(raw) == reference.get("bytes") and sha(raw) == reference.get("sha256"), "Archive bytes or hash differ")
    rows = payload.get("files")
    require(type(rows) is list, "Missing member manifest")
    by_name, folded = {}, set()
    for row in rows:
        require(type(row) is dict, "Invalid member manifest row")
        name = row.get("path")
        safe_relative(name)
        require(name.casefold() not in folded, "Duplicate package member path")
        require(type(row.get("bytes")) is int and row["bytes"] >= 0, "Invalid package member size")
        folded.add(name.casefold())
        by_name[name] = row
    require(sum(row["bytes"] for row in rows) <= MAX_UNCOMPRESSED_BYTES, "Package exceeds uncompressed bound")
    contents = {}
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        require(len(infos) == len({i.filename.casefold() for i in infos}), "Duplicate archive member")
        require({i.filename for i in infos} == set(by_name), "Archive member list differs")
        for info in infos:
            safe_relative(info.filename)
            mode = info.external_attr >> 16
            require(not info.is_dir() and not stat.S_ISLNK(mode) and not info.flag_bits & 1,
                    "Linked, directory, or encrypted archive member")
            row = by_name[info.filename]
            require(info.file_size == row["bytes"], "Archive member byte count differs")
            data = archive.read(info)
            require(len(data) == row["bytes"] and sha(data) == row.get("sha256"), "Archive member hash differs")
            contents[info.filename] = data
    condition = payload.get("condition", "original")
    require(condition in CONDITIONS, "Unknown package condition")
    artifact, protocol_path, _ = CONDITIONS[condition]
    require(payload.get("protocol_path") == protocol_path and protocol_path in contents
            and sha(contents[protocol_path]) == payload.get("protocol_sha256"), "Protocol hash binding differs")
    for tree, declaration, _ in ([CONDITIONS["original"], CONDITIONS["compat"]] if condition == "compat" else [CONDITIONS["original"]]):
        require(declaration in contents and tree + "/parent-integrity.json" in contents, "Missing packaged condition closure")
        protocol = strict(contents[declaration])
        for name, expected in protocol.get("frozen_files", {}).items():
            safe_relative(name)
            require(name in contents and sha(contents[name]) == expected, "Frozen dependency differs: " + name)
        parent = strict(contents[tree + "/parent-integrity.json"])
        for name, expected in parent.get("files", {}).items():
            safe_relative(name)
            require(name in contents and sha(contents[name]) == expected, "Parent dependency differs: " + name)
    state = _condition_state(contents, condition)
    require(all(payload.get(k) == value for k, value in state.items()), "Manifest execution state differs from packaged evidence")
    return {"status": "passed", "network_attempts": 0, "files": len(rows),
            "protocol_sha256": payload["protocol_sha256"], "annotation_state": state["annotation_state"],
            "archive_sha256": reference["sha256"]}


def verify(manifest_path):
    path = Path(manifest_path).resolve(strict=True)
    manifest = strict(path.read_bytes())
    archive = path.parent / "evidence.zip"
    require(not archive.is_symlink() and archive.is_file(), "Missing or linked evidence archive")
    return _check_manifest(manifest, archive)


def export(project=ROOT, output=None, condition="original"):
    project = Path(project).resolve(strict=True)
    require(condition in CONDITIONS, "Unknown package condition")
    artifact, protocol_path, evidence = CONDITIONS[condition]
    output = Path(output).absolute() if output is not None else project / evidence
    trees = [CONDITIONS["original"], CONDITIONS["compat"]] if condition == "compat" else [CONDITIONS["original"]]
    require(all(not output.resolve().is_relative_to(project / tree) for tree, _, _ in trees), "Output must be outside artifact inputs")
    protocol_raw = regular(project, protocol_path).read_bytes()
    protocol = strict(protocol_raw)
    for name in REQUIRED:
        regular(project, ARTIFACT + "/" + name)
    names, required_hashes = set(), {}
    for tree, declaration, _ in trees:
        names.add(declaration)
        base = project / tree
        for path in base.rglob("*"):
            require(not path.is_symlink(), "Linked artifact entry")
            if path.is_file():
                names.add(path.relative_to(project).as_posix())
        frozen = strict(regular(project, declaration).read_bytes()).get("frozen_files", {})
        parent = strict(regular(project, tree + "/parent-integrity.json").read_bytes()).get("files", {})
        for name, expected in [*frozen.items(), *parent.items()]:
            require(name not in required_hashes or required_hashes[name] == expected, "Conflicting frozen parent dependency")
            required_hashes[name] = expected
    names.update(required_hashes)
    for name in (REPORT, PDF, "README.md", "tests/test_cross_model_export.py"):
        if (project / name).is_file():
            names.add(name)
    for path in (project / "scripts").glob("*cross_model*.py"):
        names.add(path.relative_to(project).as_posix())
    for path in (project / "tests").glob("test_cross_model*.py"):
        names.add(path.relative_to(project).as_posix())
    contents, rows, folded = {}, [], set()
    for name in sorted(names):
        safe_relative(name)
        require(name.casefold() not in folded, "Case-insensitive package path collision")
        folded.add(name.casefold())
        raw = regular(project, name).read_bytes()
        require(name not in required_hashes or sha(raw) == required_hashes[name], "Frozen dependency differs: " + name)
        contents[name] = raw
        rows.append({"path": name, "bytes": len(raw), "sha256": sha(raw)})
    require(sum(row["bytes"] for row in rows) <= MAX_UNCOMPRESSED_BYTES, "Package exceeds uncompressed bound")
    state = _condition_state(contents, condition)
    replay = "scripts/reproduce_cross_model_compat.py" if condition == "compat" else "scripts/reproduce_cross_model.py"
    payload = {"format": FORMAT, "condition": condition, "protocol_path": protocol_path, "protocol_sha256": sha(protocol_raw),
               "files": rows, **state,
               "reproduction": "Extract members into an empty directory; run python " + replay + " without credentials",
               "missing_optional_files": [name for name in (REPORT, PDF, artifact + "/new-annotations.json",
                    artifact + "/ledger-final.json", artifact + "/budget-final.json", artifact + "/analysis/summary.json") if name not in contents]}
    output.mkdir(parents=True, exist_ok=True)
    require(not output.is_symlink(), "Linked evidence output directory")
    fd, temporary_name = tempfile.mkstemp(prefix=".cross-model-", suffix=".zip.tmp", dir=output)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for row in rows:
                info = zipfile.ZipInfo(row["path"], (2026, 11, 15, 0, 0, 0))
                info.create_system, info.external_attr = 3, 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, contents[row["path"]], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        raw = temporary.read_bytes()
        manifest = {"schema_version": 1, "format": FORMAT, "payload": payload, "payload_sha256": sha(encoded(payload)),
                    "archive": {"path": "evidence.zip", "bytes": len(raw), "sha256": sha(raw)}}
        _check_manifest(manifest, temporary)
        temporary.replace(output / "evidence.zip")
        manifest_path = output / "manifest.json"
        manifest_path.write_bytes(encoded(manifest))
        return manifest
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--condition", choices=tuple(CONDITIONS), default="original")
    parser.add_argument("--verify", type=Path, metavar="MANIFEST")
    args = parser.parse_args()
    if args.verify:
        result = verify(args.verify)
    else:
        manifest = export(args.project, args.output, condition=args.condition)
        result = {"manifest": str((args.output or args.project / CONDITIONS[args.condition][2]) / "manifest.json"),
                  "annotation_state": manifest["payload"]["annotation_state"], "archive": manifest["archive"]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
