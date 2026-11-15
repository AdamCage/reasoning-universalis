"""Freeze the complete exploratory design before any new annotation response."""
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cross_model.common import ARTIFACT, PARENT, PROTOCOL, ROUTES, VERSION, immutable, read, sha, utcnow


def freeze(project=ROOT):
    project = Path(project)
    base = project / ARTIFACT
    if (base / "new-annotations.json").exists():
        raise ValueError("Do not freeze or change the protocol after annotation outputs")
    paths = set(read(project / PARENT / "source-inventory.json")["files"])
    paths.update(p.relative_to(project).as_posix() for p in (project / "cross_model").glob("*.py"))
    paths.update(("scripts/collect_cross_model.py", "scripts/reproduce_cross_model.py", "scripts/freeze_cross_model.py",
                  "tests/test_cross_model_integrity.py"))
    source_files = {p: sha((project / p).read_bytes()) for p in sorted(paths)}
    immutable(base / "source-inventory.json", {"files": source_files, "version": VERSION})
    zip_path = base / "source-snapshot.zip"
    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(paths):
                info = zipfile.ZipInfo("source/" + path, (2026, 11, 15, 0, 0, 0))
                z.writestr(info, (project / path).read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    else:
        with zipfile.ZipFile(zip_path) as z:
            if any(z.read("source/"+p) != (project / p).read_bytes() for p in paths):
                raise ValueError("Existing new source snapshot differs")
    inputs = ["input-items.json", "mapping.json", "codebook.json", "selection-summary.json", "parent-integrity.json",
              "ledger-launch.json", "cost-quote.json", "source-inventory.json", "source-snapshot.zip"]
    frozen_files = {**source_files, **{ARTIFACT+"/"+p:sha((base / p).read_bytes()) for p in inputs}}
    for model, _ in ROUTES:
        path = ARTIFACT + "/metadata/" + model.replace("/", "_") + ".json"
        frozen_files[path] = sha((project / path).read_bytes())
    frozen_files[ARTIFACT + "/metadata/license-check.json"] = sha((base / "metadata/license-check.json").read_bytes())
    protocol = {"protocol_id": VERSION, "status": "frozen_exploratory_before_new_responses_budget_pending", "created_utc": utcnow(),
        "research_question": "Portability of functional labels of visible reasoning text across model-family annotation instruments",
        "parent": {"protocol": "design/MACHINE_DEVELOPMENT_PROTOCOL_2026_11_08.json", "closed_items": 200,
                   "closed_roots": 24, "human_gold": False, "E0_passed": False, "old_protocols_and_evidence_immutable": True},
        "sampling": {"unique_segments": 72, "segments_per_root": 3, "roots": 24, "core": {"items": 48, "per_root": 2,
            "algorithm": "Within root sort by SHA256(canonical([version,'core',item_id])), item_id; first two. No labels or outcomes consulted."},
            "challenge": {"items": 24, "per_root": 1, "algorithm": "Start role counts from core; among unselected items in roots not yet allocated, minimize (role_already_selected, selected_role_count, parent_role_count, SHA256([version,'challenge',item_id]),item_id), allocate its root, repeat. Unresolved reference is a category.",
                          "selection_uses_old_machine_labels": True, "prevalence_estimation": False},
            "presentation": "Core primary descriptive sample; challenge separate; pooled only explicitly enriched stress sample. No natural-role prevalence claims."},
        "annotation": {"instruments": [{"model": m, "provider": p} for m,p in ROUTES], "codebook": "unchanged parent snapshot",
            "one_independent_stateless_call_per_cell": True, "temperature": .7, "top_p": 1., "seed_requested": 2026111501,
            "seed_determinism_assumed": False, "max_tokens": 4096, "reasoning_requested_disabled": True,
            "effective_internal_reasoning": "not independently verifiable; returned reasoning flagged and never used for labels",
            "response_format": "json_schema strict; no repair, fence stripping, quote approximation, or semantic retry",
            "eligible": "HTTP200, exact returned model/provider, one choice, finish_reason stop, exact six-field JSON/schema, evidence quotes literal substrings of current segment and matching anonymous source_id",
            "forbidden_prompt_fields": ["old machine labels", "correctness", "source model/provider", "domain", "root", "future segments", "retrospective position"],
            "preservation": "Original task/current segment/max two previous segments up to1000Unicode characters copied byte-faithfully as decoded text; original Unicode offsets/provenance coordinator-side only",
            "schema_probe": "One fixed constructed item per route after budget approval, before study calls. Only technical schema/evidence validity gates route; predicted role never gates admission. Failure stops that route without substitution/retry.",
            "automatic_retries": 0},
        "context_intervention": {"reason": "All200parent items have past context; observational presence effect is unidentifiable",
            "items": 24, "one_per_root": True, "selection": "Among each root's two core items, minimum SHA256([version,'ablation',item_id]),item_id",
            "intervention": "Remove previous_segments only; task/current text/ontology/transport settings identical; original inputs preserved",
            "extra_calls": 48, "interpretation": "Paired label sensitivity; one call/condition cannot separate context effect from sampling variation"},
        "allocation": {"schema_probes": 2, "full_context": 144, "without_context": 48, "maximum_calls": 194,
                       "automatic_extension": False, "replacement_of_failed_cases": False},
        "analysis": {"primary": ["raw_agreement", "Cohen kappa", "full9x9confusion", "majority_reference_label_baseline"],
            "missingness": "Both-valid-pair agreement/kappa plus matches/all planned; unresolved reference, invalid/missing new cases counted separately, never matches. ambiguous_other is a valid ninth role.",
            "strata": ["old functional role", "source model", "domain", "segment Unicode length <=50/51-150/>150", "context Unicode length <=250/251-750/>750", "old first-panel unanimity", "reference status"],
            "uncertainty": {"method": "percentile bootstrap resampling whole original task roots with replacement, all rows and missingness retained", "replicates": 2000,
                            "seed": 20261115, "interval": .95, "undefined_replicates_reported": True, "interpretation": "descriptive dependence-aware uncertainty over observed root blocks; no IID segment inference"},
            "controls": "Fixed old DeepSeek vote0 vs vote1; vote0 vs >=3of4majority of remaining round1 votes (never includes vote0); old final consensus comparison flagged circular.",
            "paired_gap": "On same rows valid for new call, DSvote0, DSleave4, compare DSvote0-vs-leave4 agreement minus new-vs-leave4 agreement; root bootstrap, missing denominators explicit",
            "cross_family_pair": "Qwen vs GPT-OSS on same full-context items; no ground truth",
            "ablation": "Full-vs-without label change, raw agreement/kappa, full-minus-without agreement with old reference and root-bootstrap CI",
            "multiple_testing": "Exploratory descriptive estimates; no confirmatory p-values or ontology acceptance thresholds",
            "examples": "Three largest-count off-diagonal role transitions per new model; lowest versioned hash item within each transition; preserve original quote, no cherry-picking for rhetorical support"},
        "budget": {"separate_confirmation_required": True, "new_cap_rub": "400", "old_cap_is_not_authorization": True,
            "quote": ARTIFACT+"/cost-quote.json", "full_roster_reservation_rub": read(base / "cost-quote.json")["worst_case_reservation_rub"],
            "shared_state": ".research/resumption-2026-11-08-live", "keep_all_old_rows_and_unknown_reservations": True,
            "authorization_binding": "Separate artifact with explicit user instruction, protocol hash, quote hash; no fabricated approval",
            "absolute_cap": "min(3300 RUB, launch charged-or-reserved +400 RUB)"},
        "execution": {"dispatch_deadline_utc": "2026-11-15T14:03:00+00:00", "timeout_seconds": 90, "concurrency": 2,
            "single_controller_lease": True, "new_route_fallbacks": False,
            "live_metadata": "Before first paid request: fresh exact pinned-provider metadata, active/capability/context checks and no price increase above frozen ceiling"},
        "limitations": ["No human reference and no E0 pass", "visible text is not established internal state", "different model families share one infrastructure provider; parent uses another provider",
                        "single new call versus old multiseed consensus is an asymmetric comparison", "provider weight revision/quantization not independently verified", "selected exposed development roots, sparse roles, no population-validity claim"],
        "frozen_files": frozen_files}
    target = project / PROTOCOL
    if target.exists():
        prior = read(target)
        protocol["created_utc"] = prior["created_utc"]
    immutable(target, protocol)
    print({"protocol": str(target), "sha256": sha(target.read_bytes()), "frozen_files": len(frozen_files), "paid_requests": 0})
    return protocol


if __name__ == "__main__":
    freeze()
