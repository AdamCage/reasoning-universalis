"""Build allowlisted release assets from committed Git bytes, without live state."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-11-09"
EVIDENCE = "evidence/machine-annotation-development-2026-11-08/"
PROOF = "evidence/episteme-machine-annotation-2026-11-08.zip"
BOOTSTRAP = (
    "reproduce_machine_development.py", "export_machine_development.py",
    "reproduce_pilot_v2_recovery.py", "export_pilot_v2_recovery.py",
    "reproduce_pilot_v2.py", "export_pilot_v2.py", "export_local_evidence.py",
)
DOCUMENTS = (
    "reports/MACHINE_DEVELOPMENT_RESULT.md", "reports/MACHINE_REPRODUCTION_CHECK.md",
    "reports/MACHINE_VOTE_FAILURE_AUDIT.md", "reports/MACHINE_EPISTEMEOS_CHECK.md",
    "reports/POST_V2_SELECTION_ANALYSIS.md", "reports/LOCAL_RESEARCH_RESULT_RU.md",
    "reports/PILOT_V2_RECOVERY_RESULT.md", "reports/POST_V2_DESIGN_SESSION.md",
    "manuscript/LOCAL_RESEARCH_PAPER.md", "manuscript/PILOT_V2_CALIBRATION_NOTE.md",
    "manuscript/MACHINE_DEVELOPMENT_NOTE.md", "manuscript/POST_V2_DESIGN_NOTE.md",
    "design/MACHINE_DEVELOPMENT_PROTOCOL_2026_11_08.json",
    "design/POST_V2_NEXT_STAGE_2026_11_08.md",
    "design/PILOT_V3_CANDIDATE_PROTOCOL_2026_11_08.json",
    "releases/DEVELOPMENT_2026_11_09.md", "RESEARCH_SPECIFICATION.md",
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def checksums(files):
    return "".join(f"{sha(raw)}  {name}\n" for name, raw in sorted(files.items())).encode()


def write_zip(path, files):
    contents = {**files, "CONTENTS.sha256": checksums(files)}
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 9, 0, 0, 0))
            info.create_system, info.external_attr = 3, 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED if name.endswith(".zip") else zipfile.ZIP_DEFLATED
            archive.writestr(info, raw, compresslevel=9)
    with zipfile.ZipFile(path) as archive:
        if set(archive.namelist()) != set(contents) or any(archive.read(name) != raw for name, raw in contents.items()):
            raise ValueError("Release ZIP read-back differs")


def build(commit, output):
    commit = git("rev-parse", "--verify", commit + "^{commit}").decode().strip()
    names = set(git("ls-tree", "-r", "--name-only", commit).decode().splitlines())

    def blob(name):
        if name not in names:
            raise ValueError("Required committed release input missing: " + name)
        return git("show", commit + ":" + name)

    if output.exists():
        raise ValueError("Choose a new release output directory")
    output.mkdir(parents=True)
    manifest_raw, archive_raw = blob(EVIDENCE + "manifest.json"), blob(EVIDENCE + "evidence.zip")
    manifest = json.loads(manifest_raw)
    if sha(archive_raw) != manifest["archive"]["sha256"] or len(archive_raw) != manifest["archive"]["bytes"]:
        raise ValueError("Sealed machine evidence differs")
    kit = {EVIDENCE + "manifest.json": manifest_raw, EVIDENCE + "evidence.zip": archive_raw,
           "REPRODUCE.md": blob("releases/DEVELOPMENT_2026_11_09.md")}
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as sealed:
        for name in BOOTSTRAP:
            kit["scripts/" + name] = sealed.read("project/scripts/" + name)
    write_zip(output / f"machine-development-replay-{STAMP}.zip", kit)
    result_names = set(DOCUMENTS) | {name for name in names if name.startswith("artifacts/machine-annotation-development-2026-11-08/")}
    write_zip(output / f"machine-development-results-{STAMP}.zip", {name: blob(name) for name in sorted(result_names)})
    (output / Path(PROOF).name).write_bytes(blob(PROOF))
    assets = {path.name: path.read_bytes() for path in output.iterdir()}
    release = {"schema_version": 1, "source_commit": commit, "reference_runtime": "CPython 3.12.11",
               "scope": "closed exploratory development; E0 not passed; no new model calls",
               "sealed_machine_manifest_sha256": sha(manifest_raw),
               "assets": [{"path": name, "bytes": len(raw), "sha256": sha(raw)} for name, raw in sorted(assets.items())]}
    (output / "release-manifest.json").write_bytes(encoded(release))
    assets["release-manifest.json"] = (output / "release-manifest.json").read_bytes()
    (output / "SHA256SUMS.txt").write_bytes(checksums(assets))
    return release


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.commit, args.output.absolute()), indent=2))
