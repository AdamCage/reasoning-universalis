"""Audited local replay with socket guards and exact byte comparisons.

Post-seal verification driver; no model calls, state writes, or source edits.
The reproducer writes only its new output directory. This driver writes a new
receipt after every comparison succeeds. The verifier and receipt are committed
alongside the sealed snapshot. This check is not scientific review or E0.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import zipfile

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
NETWORK_ATTEMPTS = []


def deny_network(*args, **kwargs):
    NETWORK_ATTEMPTS.append("socket_operation_blocked")
    raise RuntimeError("Network disabled during offline reproduction")


socket.create_connection = deny_network
socket.getaddrinfo = deny_network
socket.getnameinfo = deny_network
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def file_digest(path):
    digest, size = hashlib.sha256(), 0
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def safe_path(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in relative,
            "Unsafe path in verification manifest")
    resolved = root / path
    require(resolved.is_file() and not resolved.is_symlink() and resolved.resolve().is_relative_to(root.resolve()),
            "Restored verification path is absent or outside the output")
    return resolved


def exact_files(paths, label):
    digests = [file_digest(path) for path in paths]
    require(len(set(digests)) == 1, label + " byte comparison failed")
    return {"sha256": digests[0][0], "bytes": digests[0][1], "exact": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PROJECT / "evidence/local-pilot-2026-11-08/manifest.json")
    parser.add_argument("--output", type=Path, default=PROJECT / ".research/local-replay-check")
    parser.add_argument("--state", type=Path, default=PROJECT / ".research/resumption-2026-11-08-live")
    parser.add_argument("--receipt", type=Path, default=PROJECT / "artifacts/resumption-2026-11-08/local/reproduction-check.json")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve(strict=True)
    output, live = args.output.absolute(), args.state.resolve(strict=True)
    require(not output.exists(), "Replay output already exists")
    require(not args.receipt.exists(), "Verification receipt already exists")
    manifest_sha, manifest_bytes = file_digest(manifest_path)
    live_ledger_before = file_digest(live / "ledger.json")
    spec = importlib.util.spec_from_file_location("guarded_local_reproduction", PROJECT / "scripts/reproduce_local.py")
    reproduction = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reproduction
    spec.loader.exec_module(reproduction)
    started = datetime.now(timezone.utc).isoformat()
    summary = reproduction.reproduce(manifest_path, output, bootstrap_samples=2000)
    require(not NETWORK_ATTEMPTS, "A network operation was attempted during replay")
    report_path = output / "reproduction.json"
    report = load(report_path)
    require(report["manifest_sha256"] == manifest_sha and len(report["analyses"]) == 5,
            "Replay did not produce the five declared analyses")
    require(report["matched_embedding_status"] == "supplementary_matched_analyses_completed"
            and set(report["embedding_modes"]) == {"baai/bge-m3", "qwen/qwen3-embedding-8b"}
            and all(mode["status"] == "reconstructed_exact" for mode in report["embedding_modes"].values()),
            "Replay omitted a completed semantic mode")
    require(report["parameters"] == {"budgets": [128, 256, 512], "bootstrap_samples": 2000, "order_controls": True},
            "Replay parameters differ from the original analyses")
    require(report["scientific_validity"] == "not_assessed" and report["E0"] == "not_passed"
            and report["network_or_model_calls"] == 0, "Replay status boundary changed")
    unpacked, local = output / "unpacked", PROJECT / "artifacts/resumption-2026-11-08/local"
    restored_state = unpacked / "state"
    manifest = load(manifest_path)
    restored_count, live_count, raw_count = 0, 0, 0
    for row in manifest["files"]:
        restored = safe_path(unpacked, row["path"])
        digest, size = file_digest(restored)
        require(digest == row["original_sha256"] and size == row["original_bytes"],
                "Independent restored original hash/size mismatch")
        restored_count += 1
        if row["path"].startswith("state/"):
            original = safe_path(live, row["path"][len("state/"):])
            require(file_digest(original) == (digest, size), "Live journal differs from restored state bytes")
            live_count += 1
            if row["path"].startswith("state/calls/"):
                raw_count += 1
    # The exact helpers shipped inside the archive must be the helpers executed.
    helper_checks = {name: exact_files([PROJECT / "scripts" / name, unpacked / "project/scripts" / name], name)
                     for name in ("export_local_evidence.py", "reproduce_local.py")}
    ledger_check = exact_files([live / "ledger.json", restored_state / "ledger.json", local / "ledger.json"], "Final ledger")
    require(live_ledger_before == file_digest(live / "ledger.json"), "Replay changed the live ledger")
    require(report["ledger_sha256_unchanged"] == ledger_check["sha256"], "Reported restored ledger digest differs")
    with zipfile.ZipFile(PROJECT / "evidence/stage0-2026-10-12.zip") as archive:
        historical_bytes = archive.read("evidence/stage0-budget.json")
    require(hashlib.sha256(historical_bytes).hexdigest() == "e062d9bdd228933ddcca0047d9ee15e564b82413bf88f92c5d06550c9febb88d",
            "Historical ledger archive identity mismatch")
    ledger = load(restored_state / "ledger.json")
    historical = json.loads(historical_bytes)
    require(ledger[:len(historical)] == historical, "Historical obligations were changed or removed")
    ledger_by_id = {row["id"]: row for row in ledger}
    require(len(ledger_by_id) == len(ledger), "Ledger repeats reservation identities")
    committed = sum((Decimal(str(row["charged_or_reserved_rub"])) for row in ledger), Decimal(0))
    require(committed.is_finite() and committed <= Decimal("3000")
            and all(Decimal(str(row["charged_or_reserved_rub"])) >= 0 for row in ledger),
            "Restored budget is invalid or exceeds the authorized shared cap")
    reservations = set()
    for path in sorted((restored_state / "calls").glob("*/reservation.json")):
        context = load(path)
        reservation_id = context["reservation_id"]
        require(reservation_id in ledger_by_id and reservation_id not in reservations,
                "Attempt reservation is absent or duplicated in the shared ledger")
        require(Decimal(ledger_by_id[reservation_id]["charged_or_reserved_rub"]) >= Decimal(context["reservation_rub"]),
                "Attempt commitment was released below its reservation")
        require(context["call_id"] == path.parent.name, "Attempt context/directory mismatch")
        reservations.add(reservation_id)
    mapping = {
        "analysis-lexical.json": "analysis-lexical.json",
        "analysis-bge.json": "analysis-baai_bge-m3.json",
        "analysis-qwen.json": "analysis-qwen_qwen3-embedding-8b.json",
        "analysis-bge-matched.json": "analysis-baai_bge-m3-matched.json",
        "analysis-qwen-matched.json": "analysis-qwen_qwen3-embedding-8b-matched.json",
    }
    analyses = []
    require({row["path"] for row in report["analyses"]} == set(mapping.values()), "Replay analysis file roster differs")
    for original_name, replay_name in mapping.items():
        published, archived, replayed = local / original_name, unpacked / "project/artifacts/resumption-2026-11-08/local" / original_name, output / replay_name
        exact = exact_files([published, archived, replayed], original_name)
        original, reproduced = load(published), load(replayed)
        require(original == reproduced, "Analysis parsed JSON differs despite byte comparison")
        require(original["scientific_status"] == "exploratory_predictive_audit_not_H1_H7_validation"
                and original["E0"] == "not_passed", "Analysis scientific scope changed")
        constant_count = sum(method.get("estimator") == "smoothed_constant_one_training_class"
                             for run in reproduced.get("runs", [])
                             for fold in run.get("folds", []) for method in fold.get("methods", {}).values())
        analyses.append({"published_path": "artifacts/resumption-2026-11-08/local/" + original_name,
                         "replay_path": replay_name, **exact, "parsed_json_equal": True,
                         "analysis_version": original["analysis_version"], "record_digest": original["record_digest"],
                         "analysis_population": original["analysis_population"],
                         "constant_training_estimators": constant_count})
    completion = load(unpacked / "bundle/derived-embedding-files.json")
    aggregates = []
    for model, audit in report["embedding_modes"].items():
        relative = model.replace("/", "_") + "-embedded.json"
        marker = next(row for row in completion["files"] if row["path"] == "state/" + relative)
        require(marker["file_present"] is True, "Completed aggregate descriptor is absent")
        digest, size = file_digest(live / relative)
        require(digest == marker["original_sha256"] == audit["original_sha256"]
                and size == marker["original_bytes"] == audit["original_bytes"],
                "Embedding aggregate live/descriptor/reconstruction hashes differ")
        aggregates.append({"model": model, "sha256": digest, "bytes": size,
                           "live_descriptor_reconstructed_exact": True})
    core = {}
    for name in ("protocol.json", "corpus.json", "source-inventory.json", "results.json"):
        core[name] = exact_files([live / name, restored_state / name], name)
    require(report["bindings"]["protocol_sha256"] == core["protocol.json"]["sha256"]
            and report["bindings"]["corpus_sha256"] == core["corpus.json"]["sha256"]
            and report["bindings"]["source_inventory_sha256"] == core["source-inventory.json"]["sha256"]
            and report["results_sha256"] == core["results.json"]["sha256"], "Replayed source/data bindings differ")
    require(not NETWORK_ATTEMPTS, "A network operation was attempted during verification")
    receipt = {"schema_version": 1, "status": "passed", "purpose": "same_code_offline_reanalysis_not_independent_replication",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_path": "evidence/local-pilot-2026-11-08/manifest.json", "manifest_sha256": manifest_sha,
        "manifest_bytes": manifest_bytes, "reproduction_report_sha256": file_digest(report_path)[0],
        "verification_program_sha256": file_digest(__file__)[0],
        "verification_program_path": "scripts/verify_local_replay.py",
        "verification_program_scope": "post-seal verifier committed alongside the external verification receipt",
        "network_guard": {"socket_connect_and_dns_disabled": True, "attempts": len(NETWORK_ATTEMPTS)},
        "thread_settings": {name: os.environ[name] for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")},
        "bootstrap_samples": 2000, "restored_files_verified": restored_count,
        "live_state_files_exact": live_count, "raw_journal_files_exact": raw_count,
        "shared_ledger": {**ledger_check, "historical_prefix_rows_retained": len(historical),
                          "new_attempt_reservations_retained": len(reservations),
                          "charged_or_reserved_rub": str(committed), "authorized_cap_rub": "3000"},
        "core_bindings": core, "executed_helper_files": helper_checks, "analyses": analyses,
        "omitted_embedding_aggregates": aggregates,
        "runtime": {"python": sys.version.split()[0], **{name: importlib.metadata.version(name)
                    for name in ("numpy", "scipy", "scikit-learn", "joblib", "threadpoolctl")}},
        "scientific_validity": "not_assessed", "E0": "not_passed", "review": "not_requested",
        "interpretation": "Exact deterministic replay establishes byte/computational consistency. It does not establish H0, equivalence, measurement validity or independent scientific review."}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False),encoding="utf-8",newline="")
    print(json.dumps({"status":"passed","receipt":str(args.receipt),"receipt_sha256":file_digest(args.receipt)[0],
                      "analyses_exact":len(analyses),"raw_files_exact":raw_count,"network_attempts":0},indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status":"failed","error_type":type(exc).__name__,"reason":str(exc),
                          "network_attempts":len(NETWORK_ATTEMPTS)}),file=sys.stderr)
        raise SystemExit(1) from None
