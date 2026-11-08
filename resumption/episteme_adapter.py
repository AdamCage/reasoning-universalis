"""Stage-only integration with the pinned upstream EpistemeOS, without kernel edits.

The optional historical command recomputes existing development observations;
it generates no new model data and records no scientific approval.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import uuid


PINNED_KERNEL_REVISION = "7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3"
PROJECT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def select_kernel(kernel_root):
    """Select a clean pinned checkout before importing any episteme module.

    This is a source/provenance check in a trusted local process, not a sandbox.
    The bundled historical kernel is deliberately left untouched.
    """
    kernel_root = Path(kernel_root).resolve(strict=True)
    revision = subprocess.check_output(
        ["git", "-C", str(kernel_root), "rev-parse", "HEAD"], text=True).strip()
    if revision != PINNED_KERNEL_REVISION:
        raise ValueError("Kernel revision differs from the explicitly pinned upstream revision")
    subprocess.run(["git", "-C", str(kernel_root), "diff", "--exit-code", "--quiet",
                    "HEAD", "--", "src", "schemas", "pyproject.toml", "uv.lock"], check=True)
    source = kernel_root / "src"
    for name, module in list(sys.modules.items()):
        if name == "episteme" or name.startswith("episteme."):
            filename = getattr(module, "__file__", None)
            if filename and not Path(filename).resolve().is_relative_to(source):
                raise RuntimeError("Another EpistemeOS is already imported; use a fresh Python process")
    sys.path.insert(0, str(source))
    episteme = importlib.import_module("episteme")
    if not Path(episteme.__file__).resolve().is_relative_to(source):
        raise RuntimeError("Imported kernel differs from the selected checkout")
    inventory = {p.relative_to(kernel_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted((source / "episteme").rglob("*.py"))}
    return {"repository": "https://github.com/AdamCage/EpistemeOS",
            "revision": revision, "python_source_inventory_sha256": hashlib.sha256(canonical(inventory)).hexdigest(),
            "isolation": "same_user_local_subprocess; no sandbox", "source_inventory": inventory}


def register_pack(pack_id, module_name):
    """Explicit application allowlist, with no mutation of the kernel registry source."""
    from episteme.domains import registry
    previous = registry.PACKS.get(pack_id)
    if previous not in (None, module_name):
        raise ValueError("Conflicting explicit pack registration")
    registry.PACKS[pack_id] = module_name
    return registry.load_pack(pack_id)


def open_frozen_stage(store, *, study, question, explanation_set, pack_id,
                      preregistration, attempt_ceiling, actor="resumption-planner",
                      predecessor=None, command_id=None):
    """Open a mechanically bounded stage over an already frozen pack protocol."""
    from episteme.kernel import Actor
    from episteme.stages import stage_open
    return stage_open(store, actor=Actor(actor, "planner"), study=study, question=question,
                      explanation_set=explanation_set, pack_id=pack_id, preregistration=preregistration,
                      attempt_ceiling=attempt_ceiling, criteria=[{"kind": "analysis_recorded"}],
                      predecessor=predecessor, command_id=command_id)


def advance_stage(store, stage_id, *, analyst="resumption-analyst",
                  executor="resumption-offline-executor", replicator="resumption-same-author-reanalysis"):
    """Resume the frozen roster without review assignment or an invented approval."""
    from episteme.kernel import Actor
    from episteme.stages import stage_run
    result = stage_run(store, stage_id, analyst=Actor(analyst, "analyst"),
                       executor=executor, replicator=replicator)
    if result["scientific_validity"] != "not_assessed" or result["review"] != "not_requested":
        raise RuntimeError("Upstream stage-only semantics changed")
    return result


def historical_smoke(kernel_root, output, contrast="S2-S1"):
    """Replay six historical GPT-OSS traces under the current stage-only API."""
    provenance = select_kernel(kernel_root)
    from episteme import domain_packs
    from episteme.commands import CommandService
    from episteme.execution_locked import freeze_closure
    from episteme.graph import ResearchGraph
    from episteme.kernel import Actor, Kernel
    from episteme.planning import Planning
    from episteme.recovery import backup
    from episteme.store import Store
    from stage2.historical import prepare
    import reasoning_universalis_v1 as pack

    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Use a new output directory; historical evidence is never overlaid")
    output.mkdir(parents=True)
    source = prepare(output / "import", archive=PROJECT / "evidence/stage0-2026-10-12.zip")
    bundle = json.loads((source / "bundle.json").read_bytes())
    loaded = register_pack(pack.PACK_ID, "reasoning_universalis_v1")
    planner = Actor("resumption-planner", "planner")
    study = "reasoning-universalis-resumption-historical-stage"
    with Store(output / "store") as store:
        planning = Planning(store, planner)
        scope = {"population": "six historical development roots only"}
        question = planning.question(study_id=study,
            statement="Does the updated stage-only controller preserve exact historical segment-count evidence?",
            objective="Validate the upstream integration mechanically; no H0-H7 inference.", scope=scope,
            constraints=["E0 not passed", "Historical development data", "No human or independent scientific review"],
            stopping_criteria=["Close after the frozen offline primary/reanalysis roster and analysis"])
        hypotheses = [Kernel(store, planner).hypothesis(text, prediction, falsifier, scope)
            for text, prediction, falsifier in [
                ("The integration preserves recorded evidence", "All raw-linked counts agree", "A byte or count mismatch"),
                ("The integration changes recorded evidence", "A byte or count mismatch", "All raw-linked counts agree")]]
        explanation = planning.explanation_set(question=question, hypotheses=hypotheses,
            comparison_plan="Check immutable captured bytes and full offline roster; retain unresolved scientific status.")
        captured = domain_packs.store_capture(store, pack.PACK_ID, source)
        environment = freeze_closure(store,
            {"pyproject.toml": pack.programs.PYPROJECT, "uv.lock": pack.programs.UV_LOCK},
            set_variables={"PYTHONHASHSEED": "0"})
        payload = {"explanation_set": explanation, "pack_id": pack.PACK_ID,
            "pack_version": loaded.pack_version, "pack_code_digest": loaded.pack_code_digest,
            "parameters": {"contrast": contrast,
                "bundle_digest": hashlib.sha256((source / "bundle.json").read_bytes()).hexdigest(),
                "method_digest": bundle["method_digest"]},
            "host_inputs": {}, "capture": captured["capture"], "environment": environment}
        registered = CommandService(store).execute({
            "context": {"command_id": uuid.uuid4().hex, "expected_revision": len(store.events()),
                "actor": planner.id, "role": planner.role, "study_id": study,
                "correlation_id": "resumption-historical-stage", "causation_id": None},
            "request": {"version": 1, "action": "pack.preregister", "payload": copy.deepcopy(payload)}})
        opened = open_frozen_stage(store, study=study, question=question, explanation_set=explanation,
            pack_id=pack.PACK_ID, preregistration=registered["binding"], attempt_ceiling=2 * len(bundle["roots"]))
        result = advance_stage(store, opened["stage"])
        # A replay of the closed stage must not dispatch again or alter its log.
        before = store.export(), store.export_receipts()
        repeated = advance_stage(store, opened["stage"])
        if before != (store.export(), store.export_receipts()) or result != repeated:
            raise RuntimeError("Closed-stage resume changed the immutable history")
        kinds = [row["kind"] for row in store.events()]
        if any(kind in {"review_assignment", "review", "paper"} for kind in kinds):
            raise RuntimeError("Stage-only run unexpectedly created review or paper")
        graph = ResearchGraph.from_store(store)
        result.update({"kernel": provenance, "pack_code_digest": loaded.pack_code_digest,
                       "network_calls": 0, "new_model_generations": 0,
                       "historical_traces": len(bundle["observations"]), "E0": "not_passed",
                       "closed_stage_replay": "same_history_no_new_attempt", "graph_snapshot_hash": graph.snapshot_hash})
        backup(store, output / "backup")
        (output / "events.jsonl").write_text(store.export(), encoding="utf-8")
    (output / "stage-result.json").write_bytes(canonical(result))
    return result


def artifact_integrity_stage(kernel_root, evidence_index, output):
    """Bind explicitly named protocol/task/result/source bytes to an audit stage.

    The index has ``artifacts`` entries with project-relative ``path``, ``role``
    and ``format`` (json or bytes). Optional sha256/bytes values are checked.
    The stage is registered after collection and checks integrity only.
    """
    provenance = select_kernel(kernel_root)
    from episteme import domain_packs
    from episteme.commands import CommandService
    from episteme.execution_locked import freeze_closure
    from episteme.graph import ResearchGraph
    from episteme.kernel import Actor, Kernel
    from episteme.planning import Planning
    from episteme.recovery import backup
    from episteme.store import Store
    import resumption_evidence_v1 as pack

    evidence_index = Path(evidence_index).resolve(strict=True)
    index_bytes = evidence_index.read_bytes()
    index = json.loads(index_bytes)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Use a new audit directory; resume an admitted stage with advance_stage")
    # Validate every input before creating any partial output or kernel event.
    captured_files = {}
    rows = []
    for entry in index["artifacts"]:
        relative = entry["path"]
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative:
            raise ValueError("Evidence paths must be relative to the research checkout")
        path = PROJECT / candidate
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(PROJECT):
            raise ValueError("Evidence must be a plain file inside the research checkout")
        data = path.read_bytes()
        row = {"path": "artifacts/" + candidate.as_posix(), "role": entry["role"],
               "format": entry["format"], "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        if ("sha256" in entry and row["sha256"] != entry["sha256"]) or ("bytes" in entry and row["bytes"] != entry["bytes"]):
            raise ValueError("Evidence differs from the index pin: " + relative)
        if row["path"] in captured_files:
            raise ValueError("Duplicate evidence path: " + relative)
        captured_files[row["path"]] = data
        rows.append(row)
    index_path = "evidence-index.json"
    captured_files[index_path] = index_bytes
    rows.append({"path": index_path, "role": "index", "format": "json",
                 "sha256": hashlib.sha256(index_bytes).hexdigest(), "bytes": len(index_bytes)})
    manifest = {"schema_version": 1, "purpose": "resumption_artifact_integrity_only",
                "scientific_validity": "not_assessed", "inference_mode": "exploratory",
                "exposure": "previously_observed; audit registered after collection",
                "artifacts": rows}
    captured_files["manifest.json"] = canonical(manifest)
    pack.inventory.verify(captured_files)
    output.mkdir(parents=True)
    source = output / "capture"
    for relative, data in captured_files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    loaded = register_pack(pack.PACK_ID, "resumption_evidence_v1")
    planner = Actor("resumption-integrity-planner", "planner")
    study = "reasoning-universalis-resumption-artifact-integrity"
    with Store(output / "store") as store:
        planning = Planning(store, planner)
        scope = {"population": "explicitly indexed previously observed research artifacts"}
        question = planning.question(study_id=study,
            statement="Do the indexed research artifacts retain their exact hashes and byte counts through offline replay?",
            objective="Preserve an auditable artifact roster, without assessing scientific validity.", scope=scope,
            constraints=list(pack.CAUTIONS), stopping_criteria=["Complete the frozen integrity-check roster, then close without review"])
        hypotheses = [Kernel(store, planner).hypothesis(text, prediction, falsifier, scope)
            for text, prediction, falsifier in [
                ("The indexed artifact bytes are preserved", "Every hash and byte count agrees", "Any mismatch"),
                ("An indexed artifact is corrupted", "At least one hash or count differs", "Every indexed artifact agrees")]]
        explanation = planning.explanation_set(question=question, hypotheses=hypotheses,
            comparison_plan="Recompute complete finite-roster byte hashes; never promote this to scientific validity.")
        captured = domain_packs.store_capture(store, pack.PACK_ID, source)
        environment = freeze_closure(store,
            {"pyproject.toml": pack.programs.PYPROJECT, "uv.lock": pack.programs.UV_LOCK},
            set_variables={"PYTHONHASHSEED": "0"})
        registered = CommandService(store).execute({
            "context": {"command_id": uuid.uuid4().hex, "expected_revision": len(store.events()),
                "actor": planner.id, "role": planner.role, "study_id": study,
                "correlation_id": "resumption-artifact-integrity", "causation_id": None},
            "request": {"version": 1, "action": "pack.preregister", "payload": {
                "explanation_set": explanation, "pack_id": pack.PACK_ID, "pack_version": loaded.pack_version,
                "pack_code_digest": loaded.pack_code_digest,
                "parameters": {"manifest_sha256": hashlib.sha256(captured_files["manifest.json"]).hexdigest()},
                "host_inputs": {}, "capture": captured["capture"], "environment": environment}}})
        opened = open_frozen_stage(store, study=study, question=question, explanation_set=explanation,
            pack_id=pack.PACK_ID, preregistration=registered["binding"], attempt_ceiling=2 * len(rows), actor=planner.id)
        result = advance_stage(store, opened["stage"])
        before = store.export(), store.export_receipts()
        repeated = advance_stage(store, opened["stage"])
        if before != (store.export(), store.export_receipts()) or repeated != result:
            raise RuntimeError("Closed integrity-stage replay changed the admitted history")
        kinds = [row["kind"] for row in store.events()]
        if any(kind in {"review_assignment", "review", "paper"} for kind in kinds):
            raise RuntimeError("Integrity stage unexpectedly created review or paper")
        graph = ResearchGraph.from_store(store)
        result.update({"kernel": provenance, "pack_code_digest": loaded.pack_code_digest,
            "evidence_index_sha256": hashlib.sha256(index_bytes).hexdigest(),
            "manifest_sha256": hashlib.sha256(captured_files["manifest.json"]).hexdigest(),
            "artifact_count": len(rows), "artifacts": rows, "network_calls": 0, "E0": "not_passed",
            "closed_stage_replay": "same_history_no_new_attempt",
            "scope": "artifact integrity only; not scientific validity, collection completeness, or preregistration of original experiment",
            "graph_snapshot_hash": graph.snapshot_hash})
        backup(store, output / "backup")
        (output / "events.jsonl").write_text(store.export(), encoding="utf-8")
    (output / "stage-result.json").write_bytes(canonical(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--historical-smoke", type=Path, metavar="OUTPUT")
    mode.add_argument("--evidence-index", type=Path)
    mode.add_argument("--resume-stage", metavar="STAGE_ID")
    parser.add_argument("--output", type=Path, help="New audit directory, required with --evidence-index")
    parser.add_argument("--store", type=Path, help="Existing Store, required with --resume-stage")
    parser.add_argument("--pack", choices=["resumption_evidence_v1", "reasoning_universalis_v1"], default="resumption_evidence_v1")
    parser.add_argument("--contrast", choices=["S2-S1", "S1-S2", "S2-S2"], default="S2-S1")
    args = parser.parse_args()
    if args.resume_stage:
        if args.store is None:
            parser.error("--store is required with --resume-stage")
        provenance = select_kernel(args.kernel_root)
        register_pack(args.pack, args.pack)
        from episteme.store import Store
        with Store(args.store) as store:
            result = advance_stage(store, args.resume_stage)
        result["kernel"] = provenance
    elif args.evidence_index:
        if args.output is None:
            parser.error("--output is required with --evidence-index")
        result = artifact_integrity_stage(args.kernel_root, args.evidence_index, args.output)
    else:
        result = historical_smoke(args.kernel_root, args.historical_smoke, args.contrast)
    compact = {key: value for key, value in result.items() if key != "kernel"}
    compact["kernel_revision"] = result["kernel"]["revision"]
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
