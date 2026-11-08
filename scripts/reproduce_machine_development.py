"""Keyless byte/schema/panel replay of machine-only development evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def sibling(name):
    spec = importlib.util.spec_from_file_location("machine_replay_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXPORT = sibling("export_machine_development")
PARENT = sibling("reproduce_pilot_v2_recovery")
require, sha, encoded = PARENT.require, PARENT.sha, PARENT.encoded


def native_path(value):
    """Keep nested immutable parent replays below no Windows path-length API limit."""
    absolute = str(Path(value).absolute())
    if os.name != "nt" or absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def worker(unpacked, output, parent_output):
    unpacked, output, parent_output = map(native_path, (unpacked, output, parent_output))
    manifest = json.loads((unpacked / "delta-manifest.json").read_bytes())
    payload = manifest["payload"]
    project, state = unpacked / "project", unpacked / "state"
    require(payload["namespace"] == "state/machine-development/" + payload["protocol_sha256"], "Unsafe machine namespace")
    scope = unpacked / payload["namespace"]
    p = json.loads((scope / "protocol.json").read_bytes())
    require(sha((scope / "protocol.json").read_bytes()) == payload["protocol_sha256"], "Machine protocol bytes differ")
    parent_ledger = parent_output / "unpacked/state/ledger.json"
    require((scope / "ledger-launch.json").read_bytes() == parent_ledger.read_bytes(), "Machine launch is not the exact sealed984-row R1 ledger")
    sys.path.insert(0, str(project))
    with PARENT.A.socket_guard() as network:
        from scripts.summarize_machine_development import build
        from stage0.traces import inspect_trace
        require(sha((state / "protocol.json").read_bytes()) == p["parent"]["protocol_sha256"]
                and sha((state / "source-inventory.json").read_bytes()) == p["parent"]["source_inventory_sha256"],
                "Inherited model-admission protocol/source proof changed")
        admission = state / "calls" / p["parent"]["admission_call_id"]
        request_raw, response_raw = (admission / "request.json").read_bytes(), (admission / "response.json").read_bytes()
        request, response = json.loads(request_raw), json.loads(response_raw)
        context, result = (json.loads((admission / name).read_bytes()) for name in ("reservation.json", "result.json"))
        retained_ids = {row["id"] for row in json.loads(parent_ledger.read_bytes())}
        require(sha(request_raw) == p["parent"]["admission_request_sha256"] == context["request_sha256"]
                and sha(response_raw) == p["parent"]["admission_response_sha256"] == result["response_sha256"]
                and result["response"] == response and context["reservation_id"] == result["reservation_id"]
                and context["reservation_id"] in retained_ids
                and request["model"] == response["json"].get("model") == p["generation"]["model"]
                and response["json"].get("provider") == p["generation"]["provider"]
                and response["http_status"] == 200 and response["json"].get("error") is None
                and inspect_trace(response["json"])["status"] == "visible_trace_candidate",
                "Original DeepSeek/BytePlus route admission/raw reservation changed")
        inputs = p["inputs"]
        summary = build(scope, project / payload["protocol_path"], project / inputs["path"],
            project / inputs["codebook"]["path"], project / inputs["mapping"]["path"], state / "ledger.json",
            output, output / "MACHINE_DEVELOPMENT_RESULT.md", source_root=project, calls=state / "calls")
        public = project / Path(inputs["path"]).parent
        for name in ("results.json", "summary.json", "budget-final.json"):
            require((public / name).is_file() and (output / name).read_bytes() == (public / name).read_bytes(),
                    "Machine frozen result/statistical summary replay is not byte-identical: " + name)
        require(not network, "Machine replay attempted network access")
    receipt = {"status": "passed", "network_attempts": len(network), "results_exact": True, "summary_exact": True,
        "synthetic_fixture": p.get("synthetic_fixture") is True,
        "results_sha256": sha((output / "results.json").read_bytes()), "summary_sha256": sha((output / "summary.json").read_bytes()),
        "all_planned_calls": summary["call_coverage"]["all_planned_slots"], "planned_items": summary["planned_items"],
        "old_ledger_prefix_rows": p["parent"]["launch_ledger_rows"],
        "source_files_exact": len(json.loads((scope / "source-inventory.json").read_bytes())["files"]),
        "charged_or_reserved_rub": json.loads((output / "budget-final.json").read_bytes())["final"]["charged_or_reserved_rub"],
        "E0": "not_passed", "human_gold": "not_created", "scientific_validity": "not_assessed"}
    (output / "worker-replay-check.json").write_bytes(encoded(receipt))
    return receipt


def reproduce(manifest_path, output):
    manifest_path, output = native_path(manifest_path).resolve(strict=True), native_path(output)
    require(not output.exists(), "Choose a new machine replay output directory")
    started = datetime.now(timezone.utc).isoformat()
    EXPORT.verify(manifest_path)
    output.mkdir(parents=True)
    EXPORT.verify(manifest_path, output / "unpacked")
    with PARENT.A.socket_guard() as network:
        parent = PARENT.reproduce(output / "unpacked/bundle/parent-R1/manifest.json", output / "parent-R1")
        require(parent["status"] == "passed" and parent["network_attempts"] == 0, "The sealed original R1 replay failed")
        program = output / "unpacked/project/scripts/reproduce_machine_development.py"
        command = [sys.executable, "-I", str(program), "--worker", str(output / "unpacked"),
                   "--output", str(output / "replayed"), "--parent-output", str(output / "parent-R1")]
        completed = subprocess.run(command, cwd=output / "unpacked/project", capture_output=True, text=True, timeout=900)
        require(completed.returncode == 0, "Fresh isolated machine replay failed: " + completed.stderr[-1800:])
        require(not network, "Parent machine replay attempted network access")
    receipt = json.loads((output / "replayed/worker-replay-check.json").read_bytes())
    receipt.update({"schema_version": 1, "bundle_manifest_sha256": sha(manifest_path.read_bytes()),
        "parent_R1_manifest_sha256": sha((output / "unpacked/bundle/parent-R1/manifest.json").read_bytes()),
        "parent_R1_replay_status": parent["status"], "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "verification_program_path": "scripts/reproduce_machine_development.py", "verification_program_sha256": sha(Path(__file__).read_bytes()),
        "scope": "same-code raw/schema/panel/budget replay, not independent annotation replication or human validation"})
    (output / "reproduction-check.json").write_bytes(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--manifest", type=Path)
    command.add_argument("--worker", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parent-output", type=Path)
    args = parser.parse_args()
    if args.worker and args.parent_output is None:
        parser.error("--worker needs --parent-output")
    result = worker(args.worker, args.output, args.parent_output) if args.worker else reproduce(args.manifest, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
