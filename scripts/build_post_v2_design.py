"""Build/check a non-executable candidate protocol and public development preview."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from post_v2_design.tasks import build, canonical, digest, structural_key
from pilot_v2.tasks import load_legacy_inventory, normalized_prompt_key, exact_instance_key, structural_fingerprint

OUTPUT = Path("artifacts/pilot-v3-design-2026-11-08")
PROTOCOL = Path("design/PILOT_V3_CANDIDATE_PROTOCOL_2026_11_08.json")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def overlap_audit(corpus, root=ROOT):
    legacy = load_legacy_inventory(root)
    v2path = root / "artifacts/pilot-v2-2026-11-08/development-tasks.json"
    v2raw = v2path.read_bytes()
    for item in json.loads(v2raw)["tasks"]:
        legacy.add(item)
    legacy.sources.append({"path": str(v2path.relative_to(root)).replace("\\", "/"), "sha256": sha(v2raw)})
    seen_roots, within_root_duplicates = {}, 0
    for item in corpus["tasks"]:
        if normalized_prompt_key(item["prompt"]) in legacy.prompts:
            raise ValueError("Historical exact prompt overlap")
        # Only logic retains the same CNF input schema. Weighted DAG checks also
        # reject a matching historical *unweighted projection*, conservatively.
        if item["domain"] == "logic":
            old_view = {"domain": "logic", "data": item["data"]}
            if exact_instance_key(old_view) in legacy.exact or structural_fingerprint(old_view) in legacy.structural:
                raise ValueError("Historical CNF instance/structural overlap")
        elif item["domain"] == "algorithms":
            old_view = {"domain": "algorithms", "data": {"nodes": item["data"]["nodes"],
                        "edges": [[a, b] for a, b, _ in item["data"]["edges"]]}}
            if structural_fingerprint(old_view) in legacy.structural:
                raise ValueError("Historical unweighted graph projection overlap")
        key = structural_key(item["domain"], item["data"])
        if key in seen_roots and seen_roots[key] != item["root_id"]:
            raise ValueError("Detected same structural root across candidate groups")
        within_root_duplicates += int(key in seen_roots)
        seen_roots[key] = item["root_id"]
    return {"status": "no_detected_overlap_within_declared_checks", "legacy": legacy.report(),
            "candidate_root_groups": len(set(seen_roots.values())), "within_root_dependent_variants": within_root_duplicates,
            "coverage": {"all_domains": "normalized exact prompt checks and new-root structural flags",
                         "logic": "legacy exact CNF and conservative WL8 structural flags",
                         "algorithms": "legacy unweighted graph projection plus weighted candidate WL8 flags",
                         "math": "new conditional/modular schema; exact new programs only",
                         "planning": "new key/door schema; candidate rotation checks only, no legacy semantic equivalence proof"},
            "limitations": "No exhaustive semantic/algebraic/isomorphism novelty or independent-family claim. New schemas are not covered by old input normalization. Historical missing-data limits remain. No model outcomes or private holdout seeds read."}


def documents(root=ROOT):
    corpus = build()
    overlap = overlap_audit(corpus, root)
    parent_path = root / "artifacts/pilot-v2-recovery-2026-11-08/budget-final.json"
    parent = json.loads(parent_path.read_bytes())
    retained = Decimal(parent["current"]["charged_or_reserved_rub"])
    proposed_additional = Decimal("600")
    files = ["post_v2_design/__init__.py", "post_v2_design/tasks.py", "scripts/build_post_v2_design.py",
             "pilot_v2/tasks.py", "scripts/pilot_v2_ledger_io_compat_v1.py"]
    files += [r["path"] for r in overlap["legacy"]["sources"] if r["path"].endswith(".py")]
    inventory = {"schema_version": 1, "scope": "Offline design-builder inputs, not an executable paid-source closure",
                 "byte_rule": "SHA256 after CRLF->LF for portable offline source identity; future execution MUST bind its actual raw source snapshot separately",
                 "files_lf_sha256": {name: sha((root / name).read_bytes().replace(b"\r\n", b"\n")) for name in sorted(set(files))}}
    models = [{"model_id": "deepseek/deepseek-v4.1-flash", "provider_candidate": "BytePlus"},
              {"model_id": "openai/gpt-oss-20b", "provider_candidate": "AkashML"}]
    roster = []
    for task in corpus["tasks"]:
        for model in models:
            for cap in (8192, 16384):
                roster.append({"cell_id": digest([corpus["corpus_sha256"], task["task_id"], model["model_id"], cap]),
                               "task_id": task["task_id"], "root_id": task["root_id"], "domain": task["domain"],
                               "tier": task["tier"], "variant": task["variant"], **model,
                               "output_budget_tokens": cap, "seed": 42, "allocation_state": "proposed_not_dispatched"})
    # Deterministic counterbalancing independent of all model outcomes.
    roster.sort(key=lambda row: digest(["post-v2-allocation-1", row["cell_id"]]))
    protocol = {"schema_version": 1, "protocol_id": "ru-compact-answer-development-v3-candidate-2026-11-08",
        "created_utc": "2026-11-08T20:28:11+00:00", "status": "offline_candidate_not_authorized_for_execution",
        "scope": "One prospective bounded development allocation, not confirmatory calibration/test, not E0 acceptance",
        "execution": {"enabled": False, "paid_collector": None, "dispatch_deadline_utc": None,
                      "new_calls_in_this_work": 0, "recovery_conditions": 0,
                      "blocking_requirements": ["fresh explicit execution deadline and concrete frozen execution plan",
                          "current RouterAI provider prices and conservative complete-roster reservations within both limits",
                          "current license, exact identity and actual non-summary reasoning-channel admission",
                          "paid collector implementation, source freeze and cross-platform locked-ledger checks",
                          "new raw-byte protocol/corpus/source binding committed before any paid response",
                          "appropriate human/gate scope before any functional-state interpretation"],
                      "no_automatic_followup": "One fixed192-cell allocation only; no support-dependent extension, repeated recovery or automatic next revision"},
        "parent": {"closed_head": "ad0d63efe3dfb1b698177ff493e5fc434690a262", "ledger_rows": parent["current"]["rows"],
                   "ledger_sha256": parent["current_ledger_sha256"], "charged_or_reserved_rub": str(retained),
                   "R1_budget_sha256": sha(parent_path.read_bytes()), "v2_A_and_R1_closed": True},
        "tasks": {"path": (OUTPUT / "development-preview.json").as_posix(), "file_sha256": sha(canonical(corpus) + b"\n"),
                  "roots": 24, "tasks": 48, "variants_per_root": 2, "domains": 4, "tiers": 3,
                  "family_change": "New compact-answer constructions; v2/v3 differences are descriptive, not a pure cap intervention",
                  "difficulty": "Controlled solver/input bounds; no empirical difficulty or error-rate guarantee",
                  "all_exposed_development": True, "holdout_seed_read": False, "final_tasks_generated": False,
                  "reference_selection": "At most64candidate draws/root for reference feasibility and structural uniqueness only; no model outcomes used"},
        "allocation": {"models": models, "output_budget_tokens": [8192, 16384], "max_calls": len(roster),
                       "attempts_per_model_cap": 48, "samples_per_cell": 1, "seed": 42,
                       "temperature": .7, "top_p": .95, "request_timeout_seconds": 180,
                       "automatic_retries": 0, "route_operational_failure_limit": 2,
                       "identity_scope": "cell IDs bind corpus digest/task/model/cap; any future collector additionally namespaces state by actual frozen raw protocol digest",
                       "route_failures": "transport/HTTP/API/identity/visibility failures; wrong, length and short-prefix outcomes are never operational errors",
                       "concurrency_max": 3, "roster_sha256": sha(canonical(roster) + b"\n")},
        "budget_proposal": {"shared_state": ".research/resumption-2026-11-08-live", "cap_total_rub": "3000",
                            "retained_charged_or_reserved_rub": str(retained), "proposed_additional_max_rub": str(proposed_additional),
                            "proposed_absolute_ceiling_rub": str(retained + proposed_additional),
                            "authorization": "Unexecuted proposal; not a fresh credit or a transfer/reset of the closed v2 envelope",
                            "price_status": "not_quoted; no claim that the planned roster fits until actual pinned quotes and reservations are checked",
                            "accounting": "Preserve984rows and all unknown reserves; no new paid state, namespace reset or automatic resend"},
        "measurement": {"primary_prefix_words": 256, "secondary_prefix_words": [128, 512],
                        "unit": "Unicode non-whitespace words, not model tokens", "answer_censor": "before first literal ANSWER:",
                        "eligible": "HTTP/API success, exact admitted model/provider, visible non-summary reasoning, finish_reason stop and gradeable final answer",
                        "length_censored_correctness": None, "force_minimum_verbosity": False,
                        "answer_grading": "Final API answer channel only; last nonempty line exact ANSWER: followed by signed decimal integer, no plus/leading zeros, max1000digits (or IMPOSSIBLE for algorithms/planning). No reasoning reconstruction; malformed/unsupported size is ungradeable, length remains null regardless of diagnostic grade.",
                        "no_short_error_exception": True, "E0": "not_passed"},
        "engineering_gate": {"minimum_completed_gradeable_fraction": .75, "denominator": "all48plannedattempts/model/cap",
                             "minimum_primary_error_roots": 3, "minimum_primary_correct_roots": 3,
                             "all192outcomes_resolved_required": True, "transport_unknown_allowed": False,
                             "scope": "engineering floor, never detector validity or power",
                             "cap_selection": "smallest common cap passing both model gates; otherwise none"},
        "future_study": {"final_N": None, "utility_margin": None, "empirical_power": None,
                         "no_heldout_release": True, "all_development_roots_excluded_from_future_test": True,
                         "E0_targets_preserved": "design/E0_PRELIMINARY.json; readiness package cannot pass40-root minimum"},
        "io_candidate": {"path": "scripts/pilot_v2_ledger_io_compat_v1.py",
                         "portable_lf_sha256": inventory["files_lf_sha256"]["scripts/pilot_v2_ledger_io_compat_v1.py"],
                         "execution_binding": "NOTbound: future paid runner must bind actual raw SHA/inventory/snapshot as required by the adapter"},
        "source_inventory_sha256": sha(canonical(inventory) + b"\n"),
        "claims_not_made": ["E0passed", "G2-G4approved", "external preregistration", "power justified", "full internal reasoning observed", "new unseen model families"]}
    return {OUTPUT / "development-preview.json": corpus, OUTPUT / "overlap-audit.json": overlap,
            OUTPUT / "source-inventory.json": inventory, OUTPUT / "proposed-roster.json": roster, PROTOCOL: protocol}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare only; do not overwrite files")
    args = parser.parse_args()
    values = documents()
    outputs = {path: canonical(value) + b"\n" for path, value in values.items()}
    manifest = {"schema_version": 1, "status": "offline_design_only_no_paid_execution", "files": {path.as_posix(): sha(raw) for path, raw in outputs.items()}}
    outputs[OUTPUT / "manifest.json"] = canonical(manifest) + b"\n"
    for path, raw in outputs.items():
        target = ROOT / path
        if args.check:
            if not target.is_file() or target.read_bytes() != raw:
                raise SystemExit(f"Offline design mismatch: {path}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    print(json.dumps({"status": "exact" if args.check else "built", "files": len(outputs), "new_model_calls": 0, "paid_execution_enabled": False}))


if __name__ == "__main__":
    main()
