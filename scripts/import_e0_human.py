"""Strict human handoff import/release; identity verification and E0 stay pending."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path, PurePosixPath
import random
import shutil
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from measurement.evaluation import boundary_f1, cohen_kappa
from measurement.lexical import ROLES

spec = importlib.util.spec_from_file_location("e0_human_preparation", Path(__file__).with_name("prepare_e0_human.py"))
PREP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PREP)
require, sha, load, write = PREP.require, PREP.sha, PREP.load, PREP.write


def checked_relative(root, name):
    require(isinstance(name, str) and "\\" not in name and "\x00" not in name, "Unsafe handoff path")
    parts = PurePosixPath(name)
    require(parts.parts and not parts.is_absolute() and parts.as_posix() == name
            and all(part not in (".", "..") and ":" not in part and not part.endswith((".", " ")) for part in parts.parts),
            "Unsafe handoff path")
    path = root / parts
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), "Handoff path is absent or outside package")
    return path


def check_package(root):
    root = Path(root).resolve(strict=True)
    manifest = load(root / "coordinator/package-manifest.json")
    require(manifest.get("version") == PREP.VERSION and manifest.get("E0") == "pending", "Unknown or falsely accepted human package")
    files = manifest["files"]
    names = [row["path"] for row in files]
    require(len(names) == len(set(name.casefold() for name in names)), "Repeated handoff file path")
    for row in files:
        data = checked_relative(root, row["path"]).read_bytes()
        require(len(data) == row["bytes"] and sha(data) == row["sha256"], "Handoff file changed")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    require(actual == set(names) | {"coordinator/package-manifest.json"}, "Unlisted file in immutable handoff package")
    mapping = load(root / "coordinator/source-map.json")
    provenance = load(root / "coordinator/source-provenance.json")
    expected_sources = {value["snapshot_path"]: value["sha256"] for label, value in provenance["sources"].items()
                        if label not in ("results", "tasks", "raw_replay_proof")}
    with zipfile.ZipFile(root / "coordinator/method-sources.zip") as archive:
        require(len(archive.infolist()) == len(expected_sources) and set(archive.namelist()) == set(expected_sources),
                "Method source snapshot roster differs")
        require(all(sha(archive.read(name)) == digest for name, digest in expected_sources.items()),
                "Method source snapshot bytes differ")
        runtime_sources = {
            "handoff_creator": Path(PREP.__file__),
            "handoff_importer": Path(__file__),
            "measurement_core": Path(sys.modules["measurement.core"].__file__),
            "measurement_evaluation": Path(sys.modules["measurement.evaluation"].__file__),
            "measurement_ontology": Path(sys.modules["measurement.lexical"].__file__),
        }
        for label, runtime_path in runtime_sources.items():
            captured = archive.read(provenance["sources"][label]["snapshot_path"])
            require(captured.replace(b"\r\n", b"\n") == runtime_path.read_bytes().replace(b"\r\n", b"\n"),
                    "Runtime method source differs beyond the declared CRLF-to-LF compatibility")
    for slot in ("A", "B"):
        boundaries = load(root / "public-boundary" / slot / "items.json")
        roles = load(root / "coordinator/role-round2-prepared" / slot / "items.json")
        traces = {item["item_id"]: item for item in boundaries["items"]}
        require(len(traces) == 24 and len(roles["items"]) == 200, "Development handoff roster changed")
        for trace_id, item in traces.items():
            source = mapping["traces"][trace_id]
            require(sha(item["text"].encode("utf-8")) == item["text_sha256"] == source["source_text_sha256"],
                    "Exact boundary text binding differs")
        for item in roles["items"]:
            source = mapping["roles_s2"][item["item_id"]]
            trace = traces[source["trace_item_id"]]["text"]
            start, end = source["char_start"], source["char_end"]
            current = item["current_segment"]["text"]
            require(type(start) is int and type(end) is int and 0 <= start < end <= len(trace)
                    and trace[start:end] == current and sha(current.encode("utf-8")) == source["text_sha256"],
                    "S2 Unicode text/offset binding differs")
            context = "".join(previous["text"] for previous in item["previous_segments"])
            require(len(item["previous_segments"]) <= 2 and len(context) <= 1000
                    and sha(context.encode("utf-8")) == source["previous_context_sha256"]
                    and (not context or trace[:start].endswith(context)), "S2 past context binding differs")
    return root, manifest, mapping


def timestamp(value):
    require(isinstance(value, str) and value, "Human completion timestamp is missing")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PREP.HandoffError("Human completion timestamp is malformed") from None
    require(result.tzinfo is not None, "Human completion timestamp must include timezone")
    return result


def validate(root, manifest, slot, round_name, response_path):
    require(slot in ("A", "B") and round_name in ("boundaries", PREP.ROLE_ROUND), "Unknown slot or annotation round")
    packet_path = (root / "public-boundary" / slot / "items.json" if round_name == "boundaries"
                   else root / "coordinator/role-round2-prepared" / slot / "items.json")
    packet, submission = load(packet_path), load(response_path)
    require(set(submission) == {"schema_version", "package_id", "slot", "round", "packet_sha256", "status", "human_attestation", "responses"}
            and submission["schema_version"] == 1 and submission["package_id"] == manifest["package_id"]
            and submission["slot"] == slot and submission["round"] == round_name
            and submission["packet_sha256"] == sha(packet_path.read_bytes()), "Submission packet/round/slot provenance differs")
    require(submission["status"] == "completed", "Empty or incomplete form is not a human submission")
    actor = submission["human_attestation"]
    require(isinstance(actor, dict) and set(actor) == set(PREP.ATTESTATION), "Missing human self-report fields")
    require(isinstance(actor["participant_pseudonym"], str) and bool(actor["participant_pseudonym"].strip()),
            "No real participant has supplied a pseudonym")
    for field in PREP.ATTESTATION:
        if field not in ("participant_pseudonym", "completed_utc"):
            require(actor[field] is True, "Human independence/training/no-role-before-boundary self-report is missing")
    timestamp(actor["completed_utc"])
    items = {item["item_id"]: item for item in packet["items"]}
    rows = submission["responses"]
    require(type(rows) is list and len(rows) == len(items) and len({row.get("item_id") for row in rows}) == len(items)
            and {row.get("item_id") for row in rows} == set(items), "Missing, repeated, or foreign annotation item")
    schema = load(root / "coordinator/role-schema-snapshot.json")["properties"]
    for row in rows:
        common = {"item_id", "completed", "comment"}
        expected = common | ({"boundaries", "uncertain_boundaries"} if round_name == "boundaries" else
                             {"primary_role", "secondary_roles", "confidence", "reason_code", "explanation", "evidence_quotes", "context_extended"})
        require(set(row) == expected and row["completed"] is True and isinstance(row["comment"], str),
                "Annotation item is incomplete or has an unexpected field")
        item = items[row["item_id"]]
        if round_name == "boundaries":
            for field in ("boundaries", "uncertain_boundaries"):
                offsets = row[field]
                require(type(offsets) is list and all(type(value) is int and 0 < value < len(item["text"]) for value in offsets)
                        and offsets == sorted(set(offsets)), "Invalid independent Unicode boundary")
        else:
            primary, secondary = row["primary_role"], row["secondary_roles"]
            require(primary in ROLES and type(secondary) is list and len(secondary) <= 3
                    and len(secondary) == len(set(secondary)) and all(role in ROLES[:-1] and role != primary for role in secondary),
                    "Invalid human primary/secondary role")
            require(row["confidence"] in schema["confidence"]["enum"] and row["reason_code"] in schema["reason_code"]["enum"]
                    and isinstance(row["explanation"], str) and bool(row["explanation"].strip())
                    and type(row["context_extended"]) is bool, "Missing human rubric/context response")
            if row["context_extended"]:
                require(len(row["explanation"].strip()) >= 10, "Full-context use needs an explicit account")
            quotes = row["evidence_quotes"]
            require(type(quotes) is list and 1 <= len(quotes) <= 3, "Human evidence quote missing")
            for quote in quotes:
                require(set(quote) == {"source_id", "quote"} and quote["source_id"] == item["item_id"]
                        and isinstance(quote["quote"], str) and 1 <= len(quote["quote"]) <= 400
                        and quote["quote"] in item["current_segment"]["text"], "Human quote is not in the current segment")
    return submission


def pair(root, manifest, round_name, left_path, right_path):
    left, right = (validate(root, manifest, slot, round_name, path) for slot, path in (("A", left_path), ("B", right_path)))
    require(left["human_attestation"]["participant_pseudonym"].strip().casefold() !=
            right["human_attestation"]["participant_pseudonym"].strip().casefold(),
            "Two distinct self-reported human participants are required")
    require(sha(Path(left_path).read_bytes()) != sha(Path(right_path).read_bytes()), "A single response file cannot provide two independent submissions")
    return left, right


def release_roles(package, boundary_a, boundary_b, output, *, synthetic_released_utc=None):
    root, manifest, mapping = check_package(package)
    left, right = pair(root, manifest, "boundaries", boundary_a, boundary_b)
    released = datetime.now(timezone.utc)
    if synthetic_released_utc is not None:
        require(manifest["synthetic_fixture"], "Only synthetic tests may supply a release clock")
        released = timestamp(synthetic_released_utc)
    require(released >= max(timestamp(value["human_attestation"]["completed_utc"]) for value in (left, right)),
            "Release cannot precede either declared independent boundary completion")
    output = Path(output).absolute()
    require(not output.exists() and not output.is_relative_to(root), "Use a new role-release directory outside the frozen package")
    for slot in ("A", "B"):
        shutil.copytree(root / "coordinator/role-round2-prepared" / slot, output / slot)
    for slot, path in (("A", boundary_a), ("B", boundary_b)):
        (output / ("boundary-" + slot + ".original.private.json")).write_bytes(Path(path).read_bytes())
    receipt = {"schema_version": 1, "package_id": manifest["package_id"], "round": PREP.ROLE_ROUND,
        "status": "synthetic_fixture_only" if manifest["synthetic_fixture"] else "released_on_self_reports_identity_verification_pending",
        "synthetic_fixture": manifest["synthetic_fixture"], "E0": "pending", "actor_identity_verification": "coordinator_pending",
        "released_utc": released.isoformat(),
        "boundary_submissions": {slot: {"sha256": sha(Path(path).read_bytes()),
            "participant_pseudonym": submission["human_attestation"]["participant_pseudonym"],
            "completed_utc": submission["human_attestation"]["completed_utc"]}
            for slot, path, submission in (("A", boundary_a, left), ("B", boundary_b, right))},
        "role_packets": {slot: sha((output / slot / "items.json").read_bytes()) for slot in ("A", "B")},
        "full_context_policy": "obtain exact selected trace from coordinator only; retain explanation and analyze extensions separately"}
    write(output / "release-receipt.private.json", receipt)
    return {"status": receipt["status"], "role_packets": 2, "human_identity_verified": False, "E0": "pending"}


def record_one(package, slot, round_name, response_path, output):
    """Preserve the first submission separately, without opening a peer's file."""
    require(round_name == "boundaries", "Record boundary submissions first; role import requires the release receipt")
    root, manifest, mapping = check_package(package)
    submission = validate(root, manifest, slot, round_name, response_path)
    output = Path(output).absolute()
    require(not output.exists() and not output.is_relative_to(root), "Use a new private receipt directory outside the package")
    output.mkdir(parents=True)
    data = Path(response_path).read_bytes()
    (output / "submission.original.private.json").write_bytes(data)
    receipt = {"schema_version": 1, "package_id": manifest["package_id"], "round": round_name, "slot": slot,
               "status": "synthetic_fixture_only" if manifest["synthetic_fixture"] else "recorded_self_report_identity_pending",
               "synthetic_fixture": manifest["synthetic_fixture"], "recorded_utc": datetime.now(timezone.utc).isoformat(),
               "submission_sha256": sha(data), "peer_submission_opened": False, "agreement": "not_evaluated",
               "human_identity_verified": False, "E0": "pending"}
    write(output / "receipt.private.json", receipt)
    return {key: receipt[key] for key in ("status", "agreement", "human_identity_verified", "E0")}


def agreement(left, right, mapping, round_name):
    a, b = ({row["item_id"]: row for row in submission["responses"]} for submission in (left, right))
    if round_name == "boundaries":
        rows = [{"trace_item_id": item_id, **boundary_f1(a[item_id]["boundaries"], b[item_id]["boundaries"],
                 mapping["traces"][item_id]["source_text_characters"]),
                 "no_internal_boundaries_both": not a[item_id]["boundaries"] and not b[item_id]["boundaries"]}
                for item_id in sorted(a)]
        return {"human_vs_human_boundary_agreement": rows, "boundary_accuracy_against_adjudicated_gold": None,
                "S1_recovery_validated": False}
    pairs = [(a[item_id]["primary_role"], b[item_id]["primary_role"]) for item_id in sorted(a)]
    result = cohen_kappa(pairs)
    result["per_role"] = {role: {"annotator_A": sum(x == role for x, y in pairs),
                                "annotator_B": sum(y == role for x, y in pairs),
                                "same_label": sum(x == y == role for x, y in pairs)} for role in ROLES}
    groups = defaultdict(list)
    for item_id in sorted(a):
        groups[mapping["roles_s2"][item_id]["root_id"]].append((a[item_id]["primary_role"], b[item_id]["primary_role"]))
    roots, rng, values = sorted(groups), random.Random(20261012), []
    for _ in range(1000):
        sample = [item for __ in roots for item in groups[rng.choice(roots)]]
        values.append(cohen_kappa(sample))
    result["root_bootstrap"] = {"unit": "original_task_root", "roots": len(roots), "replicates": 1000, "seed": 20261012}
    for key in ("raw_agreement", "cohen_kappa"):
        scores = sorted(value[key] for value in values if value[key] is not None)
        result["root_bootstrap"][key + "_interval"] = ([scores[int(.025 * (len(scores) - 1))], scores[int(.975 * (len(scores) - 1))]]
                                                       if len(roots) >= 2 and scores else None)
        result["root_bootstrap"][key + "_defined_replicates"] = len(scores)
    result["full_context_extended"] = {slot: sum(row["context_extended"] for row in submission["responses"])
                                       for slot, submission in (("A", left), ("B", right))}
    result.update(macro_f1_against_adjudicated_human_gold=None, S1_roles_validated=False,
                  natural_ambiguous_prevalence_estimated=False)
    return result


def import_pair(package, round_name, response_a, response_b, output, release_receipt=None):
    root, manifest, mapping = check_package(package)
    left, right = pair(root, manifest, round_name, response_a, response_b)
    if round_name == PREP.ROLE_ROUND:
        require(release_receipt is not None, "Two boundary submissions and their role-release receipt are required first")
        receipt = load(release_receipt)
        require(receipt["package_id"] == manifest["package_id"] and receipt["round"] == PREP.ROLE_ROUND
                and receipt["E0"] == "pending" and receipt["synthetic_fixture"] == manifest["synthetic_fixture"],
                "Role-release provenance differs")
        boundary_paths = [Path(release_receipt).parent / ("boundary-" + slot + ".original.private.json") for slot in ("A", "B")]
        boundary_pair = pair(root, manifest, "boundaries", *boundary_paths)
        both_boundaries_completed = max(timestamp(boundary["human_attestation"]["completed_utc"]) for boundary in boundary_pair)
        release_completed = max(both_boundaries_completed, timestamp(receipt["released_utc"]))
        for slot, submission in (("A", left), ("B", right)):
            expected = receipt["boundary_submissions"][slot]
            require(receipt["role_packets"][slot] == submission["packet_sha256"]
                    and expected["participant_pseudonym"] == submission["human_attestation"]["participant_pseudonym"]
                    and timestamp(submission["human_attestation"]["completed_utc"]) >= release_completed,
                    "Role response changes participant or predates both independent boundary completions or actual release")
        for slot, path, boundary in zip(("A", "B"), boundary_paths, boundary_pair):
            require(sha(path.read_bytes()) == receipt["boundary_submissions"][slot]["sha256"]
                    and boundary["human_attestation"]["participant_pseudonym"] == receipt["boundary_submissions"][slot]["participant_pseudonym"]
                    and boundary["human_attestation"]["completed_utc"] == receipt["boundary_submissions"][slot]["completed_utc"],
                    "Role release no longer preserves its original independent boundary submissions")
    output = Path(output).absolute()
    require(not output.exists() and not output.is_relative_to(root), "Use a new import directory outside the frozen package")
    output.mkdir(parents=True)
    for slot, path in (("A", response_a), ("B", response_b)):
        (output / (slot + ".original.json")).write_bytes(Path(path).read_bytes())
    result = {"schema_version": 1, "package_id": manifest["package_id"], "round": round_name,
              "status": "synthetic_fixture_not_human_data" if manifest["synthetic_fixture"] else "self_reported_submissions_imported_identity_pending",
              "synthetic_fixture": manifest["synthetic_fixture"], "actor_identity_verification": "coordinator_pending",
              "adjudication": "not_started", "human_gold": "not_adjudicated", "E0": "pending",
              "human_identity_verified": False, "independence_verified": False,
              "agreement_stage": "pre_adjudication_only", "metrics": agreement(left, right, mapping, round_name),
              "source_submissions": {slot: sha(Path(path).read_bytes()) for slot, path in (("A", response_a), ("B", response_b))}}
    write(output / "pre-adjudication.private.json", result)
    return {"status": result["status"], "items": len(left["responses"]), "human_identity_verified": False, "E0": "pending"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--check-package", action="store_true")
    command.add_argument("--release-roles", action="store_true")
    command.add_argument("--import-pair", action="store_true")
    command.add_argument("--record-one", action="store_true")
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--response-a", type=Path)
    parser.add_argument("--response-b", type=Path)
    parser.add_argument("--round", choices=("boundaries", PREP.ROLE_ROUND))
    parser.add_argument("--slot", choices=("A", "B"))
    parser.add_argument("--release-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.record_one and (not args.response_a or not args.slot or not args.round or not args.output):
        parser.error("--record-one requires --response-a --slot --round --output")
    if not args.check_package and not args.record_one and (not args.response_a or not args.response_b or not args.output):
        parser.error("release/import requires --response-a --response-b --output")
    if args.import_pair and args.round is None:
        parser.error("--import-pair requires --round")
    try:
        if args.check_package:
            root, manifest, mapping = check_package(args.package)
            result = {"status": "prepared_pending_humans", "E0": "pending", "files": len(manifest["files"]),
                      "roots": len({row["root_id"] for row in mapping["traces"].values()}), "human_metrics": "not_evaluated",
                      "source_scope": "exact archived bytes and normalized-CRLF-to-LF current method code; not execution attestation"}
        elif args.release_roles:
            result = release_roles(args.package, args.response_a, args.response_b, args.output)
        elif args.record_one:
            result = record_one(args.package, args.slot, args.round, args.response_a, args.output)
        else:
            result = import_pair(args.package, args.round, args.response_a, args.response_b, args.output, args.release_receipt)
    except (PREP.HandoffError, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc) if isinstance(exc, PREP.HandoffError) else type(exc).__name__, "E0": "pending"}))
        raise SystemExit(2) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
