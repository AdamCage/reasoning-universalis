"""Offline primary-A replay followed by the separately frozen R1 supplement.

DeepSeek records retain exact A physical provenance. New GPT observations use
R1 protocol/source/route identities, while their inherited physical phase field
remains explicitly documented as legacy. This check is not scientific review.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import zipfile


def sibling(name):
    spec = importlib.util.spec_from_file_location("R1_" + name, Path(__file__).with_name(name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


A = sibling("reproduce_pilot_v2")
EXPORT = sibling("export_pilot_v2_recovery")
require, sha, encoded, load = A.require, A.sha, A.encoded, A.load
GPT, DS = "openai/gpt-oss-20b", "deepseek/deepseek-v4.1-flash"
PHASE = "pilot_v2_provider_recovery_R1"
SCRIPT = "scripts/collect_pilot_v2_recovery.py"


def replay_recovery(unpacked, output, manifest, parent_output):
    payload = manifest["payload"]
    protocol_hash = payload["protocol_sha256"]
    require(payload["namespace"] == "state/pilot-v2-recovery/" + protocol_hash, "Unsafe R1 namespace")
    state, scope = unpacked / "state", unpacked / payload["namespace"]
    parent_state = parent_output / "unpacked/state"
    protocol = load(scope / "protocol.json")
    p = protocol["recovery"]
    require(protocol["status"] == "prospective_frozen_provider_recovery" and p["condition"] == "R1",
            "R1 protocol is not finalized")
    require(sha((scope / "protocol.json").read_bytes()) == protocol_hash
            and (scope / "protocol.json").read_bytes() ==
            (unpacked / "project" / EXPORT.PROTOCOL).read_bytes(), "Public/bound R1 protocol differs")
    require(payload["primary_A_manifest_sha256"] == p["parent_delta_manifest_sha256"]
            == sha((unpacked / "bundle/parent-A/manifest.json").read_bytes()), "Primary-A seal binding differs")
    require(p["parent_scope"] == "pilot-v2/" + p["parent_protocol_sha256"], "Unsafe original-A namespace")
    a_scope = parent_state / p["parent_scope"]
    a_protocol, a_results, a_plan, a_inventory = (load(a_scope / name) for name in
        ("protocol.json", "results.json", "dispatch-plan.json", "source-inventory.json"))
    for name, field in (("protocol.json", "parent_protocol_sha256"), ("results.json", "parent_results_sha256"),
                        ("dispatch-plan.json", "parent_dispatch_plan_sha256"),
                        ("source-inventory.json", "parent_source_inventory_sha256")):
        require(sha((a_scope / name).read_bytes()) == p[field], "Original A artifact changed")
    inventory, plan, results, mapping = (load(scope / name) for name in
        ("source-inventory.json", "dispatch-plan.json", "results.json", "reuse-mapping.json"))
    source = scope / "source"
    require(sha((scope / "source-inventory.json").read_bytes()) == payload["source_inventory_sha256"], "R1 source inventory binding differs")
    require(inventory["files"] == {**a_inventory["files"], SCRIPT: p["collector_sha256"]}, "R1 changed original frozen source closure")
    for name, digest in inventory["files"].items():
        EXPORT.safe_relative(name)
        require(sha((source / name).read_bytes()) == digest and
                (source / name).read_bytes() == (unpacked / "project" / name).read_bytes(), "Frozen R1 source bytes differ")
    require({path.relative_to(source).as_posix() for path in source.rglob("*.py")} == set(inventory["files"]),
            "Unlisted R1 Python source")
    corpus_path = scope / "corpus.json"
    require(corpus_path.read_bytes() == (a_scope / "corpus.json").read_bytes() ==
            (unpacked / "project" / protocol["tasks"]["path"]).read_bytes(), "R1 corpus differs from A")
    decision_path = unpacked / "project" / EXPORT.safe_relative(p["decision_path"])
    decision = load(decision_path)
    require(sha(decision_path.read_bytes()) == p["decision_sha256"]
            and decision["status"] == "design_recovery_condition_before_class_tally"
            and decision["original_condition_sha256"] == p["parent_protocol_sha256"]
            and decision["original_results_sha256"] == p["parent_results_sha256"], "Prospective recovery decision binding differs")
    registry = load(state / "pilot-v2-recovery/condition-R1.json")
    require(registry == {"schema_version": 1, "condition": "R1", "protocol_sha256": protocol_hash,
                         "decision_sha256": p["decision_sha256"], "parent_protocol_sha256": p["parent_protocol_sha256"]},
            "One-condition shared R1 registry differs")
    parent = protocol["parent"]
    require(payload["v1_bundle_manifest_sha256"] == parent["v1_raw_bundle_manifest_sha256"] ==
            a_protocol["parent"]["v1_raw_bundle_manifest_sha256"], "Original v1 bundle binding differs")
    launch_path = scope / "ledger-launch.json"
    require(launch_path.read_bytes() == (parent_state / "ledger.json").read_bytes()
            and sha(launch_path.read_bytes()) == parent["launch_ledger_sha256"], "R1 launch did not retain the exact closed-A ledger")
    launch, rows = load(launch_path), load(state / "ledger.json")
    require(len(launch) == parent["launch_ledger_rows"] and rows[:len(launch)] == launch, "Closed-A ledger prefix changed")
    ledger = {row["id"]: row for row in rows}
    require(len(ledger) == len(rows), "Repeated shared reservation ID")
    amounts = [Decimal(row["charged_or_reserved_rub"]) for row in rows]
    require(all(value.is_finite() and value >= 0 for value in amounts), "Invalid retained commitment")
    committed = sum(amounts, Decimal(0))
    require(str(committed) == results["charged_or_reserved_rub"] and
            sum((Decimal(row["charged_or_reserved_rub"]) for row in launch), Decimal(0)) ==
            Decimal(parent["launch_charged_or_reserved_rub"]), "R1 accounting differs from retained shared ledger")
    for section in ("statistical_plan", "planning_scenarios"):
        if section in protocol:
            item = protocol[section]
            require(sha((unpacked / "project" / EXPORT.safe_relative(item["path"])).read_bytes()) == item["sha256"],
                    "Frozen public R1 design artifact differs")
    a_records = {row["trace_id"]: row for row in a_results["records"]}
    require(len(a_records) == 192 and all(row.get("request_state") != "unknown"
            and row["status"] not in ("unresolved_intent", "unresolved_attempt") for row in a_records.values()),
            "Original A unknowns preclude this recovery")
    reused = [row for row in a_records.values() if row["model"] == DS]
    attempted_gpt = [row for row in a_records.values() if row["model"] == GPT and row.get("attempted") is True]
    require(len(reused) == 96 and all(row.get("attempted") is True for row in reused) and len(attempted_gpt) == 2,
            "R1 does not retain declared DS96 plus two known parent GPT failures")
    for row in attempted_gpt:
        response = load(parent_state / "calls" / row["trace_id"] / "response.json")
        error = response.get("json", {}).get("error")
        require(response.get("http_status") is not None and not response.get("network_error")
                and (response["http_status"] == 503 or isinstance(error, dict) and str(error.get("code")) == "503"),
                "Parent GPT failure was not the declared known503 outcome")
    referenced, finalized, unattempted, unresolved = set(), [], [], []
    with A.frozen_runtime(source) as (tasks_module, stats, runtime):
        runtime.update({"PilotV2Runner": runtime["FrozenClassifier"], "PROJECT": unpacked / "project",
                        "SCRIPT": SCRIPT, "STATUS": "prospective_frozen_provider_recovery", "PHASE": PHASE,
                        "GPT": GPT, "DEEPSEEK": DS, "ROUTES": {GPT: "AkashML", DS: "BytePlus"}})
        A.selected_definitions(source / SCRIPT, {"RecoveryRunner"}, runtime)
        classifier = runtime["RecoveryRunner"].__new__(runtime["RecoveryRunner"])
        classifier.protocol, classifier.protocol_digest = protocol, protocol_hash
        classifier.a_protocol, classifier.a_results, classifier.a_plan = a_protocol, a_results, a_plan
        classifier.corpus_path = corpus_path
        classifier._validate_contract(decision)
        classifier.tasks_digest = sha(corpus_path.read_bytes())
        classifier.source_inventory_digest = payload["source_inventory_sha256"]
        classifier.verifier_source_digest = inventory["files"]["pilot_v2/tasks.py"]
        classifier.model_specs = {spec["model"]: spec for spec in protocol["models"]}
        tasks, ordered = runtime["corpus_tasks"](load(corpus_path))
        stats.validate_probe_layout(tasks)
        classifier.task_lookup = {task["task_id"]: task for task in tasks}
        generated = runtime["FrozenClassifier"]._make_plan(classifier, ordered)
        old_cells = {classifier.key(cell): cell for cell in a_plan["cells"]}
        mixed = []
        for cell in generated["cells"]:
            old = old_cells[classifier.key(cell)]
            require(cell["seed"] == old["seed"], "R1 changed original paired sampling seed")
            mixed.append(old if cell["model"] == DS else cell)
        expected_plan = {**generated, "phase": PHASE, "new_calls": 96, "reused_records": 96,
                         "physical_record_phase_policy": "Inherited classifier phase is legacy; protocol SHA and R1 mapping define membership",
                         "cells": mixed}
        require(runtime["encode"](expected_plan) == (scope / "dispatch-plan.json").read_bytes(), "Frozen R1 all192 roster differs")
        classifier.plan = expected_plan
        classifier.new_cells = [cell for cell in mixed if cell["model"] == GPT]
        require(runtime["encode"](classifier._reuse_mapping()) == (scope / "reuse-mapping.json").read_bytes(),
                "Exact original reuse/new96 lineage mapping differs")
        new_ids = {cell["call_id"] for cell in classifier.new_cells}
        require(all(path.stem in new_ids for path in (scope / "intents").glob("*.json")), "Unmapped R1 intent")
        require(results["phase"] == PHASE and results["condition"] == "R1" and results["all_planned_cells"] == 192
                and results["new_planned_calls"] == results["reused_records"] == 96 and results["independent_roots"] == 24
                and results["parent_results_sha256"] == p["parent_results_sha256"]
                and results["protocol_sha256"] == protocol_hash and results["corpus_sha256"] == classifier.tasks_digest
                and results["source_inventory_sha256"] == classifier.source_inventory_digest
                and results["dispatch_plan_sha256"] == sha((scope / "dispatch-plan.json").read_bytes())
                and results["reuse_mapping_sha256"] == sha((scope / "reuse-mapping.json").read_bytes())
                and results["physical_record_phase_policy"] == plan["physical_record_phase_policy"]
                and len(results["records"]) == 192
                and [row["trace_id"] for row in results["records"]] == [cell["call_id"] for cell in mixed],
                "R1 mixed-provenance header/roster binding differs")
        spec = classifier.model_specs[GPT]
        directory = state / "calls" / spec["parent_admission_call_id"]
        request, response, context, result = A.check_call(directory, ledger, protocol_hash=parent["protocol_sha256"])
        require(sha((directory / "request.json").read_bytes()) == spec["parent_request_sha256"]
                and sha((directory / "response.json").read_bytes()) == spec["parent_response_sha256"]
                and request["model"] == response["json"].get("model") == GPT and response["json"].get("provider") == "AkashML"
                and response["http_status"] == 200 and response["json"].get("error") is None
                and request.get("reasoning", {}).get("enabled") is True and request.get("include_reasoning") is True
                and runtime["inspect_trace"](response["json"])["status"] == "visible_trace_candidate",
                "Inherited AkashML physical route admission differs")
        require({path.name for path in (state / "calls").iterdir() if path.is_dir()} <=
                new_ids | {spec["parent_admission_call_id"]}, "Unexpected R1 raw call directory")
        classifier.calls, classifier.scope = output / "scratch/calls", output / "scratch/scope"
        classifier.fixture_verifier, classifier.locked = None, nullcontext
        classifier.save = lambda path, value: sha(runtime["encode"](value))
        classifier._route_state = lambda: {"schema_version": 1, "operational_failure_calls": {}}
        regenerated, legacy_phase_count = [], 0
        for cell, record in zip(mixed, results["records"]):
            if cell["model"] == DS:
                require(record == a_records[cell["call_id"]], "A reused DeepSeek physical record was altered")
                regenerated.append(a_records[cell["call_id"]])
                continue
            directory = state / "calls" / cell["call_id"]
            intent_path = scope / "intents" / (cell["call_id"] + ".json")
            if (directory / "result.json").is_file():
                request, response, context, result = A.check_call(directory, ledger, protocol_hash=protocol_hash)
                require(runtime["encode"](classifier.body(cell)) == (directory / "request.json").read_bytes()
                        and context["kind"] == "pilot_v2_generation" and context["identity"] == [cell["condition_id"], 0]
                        and context["corpus_sha256"] == classifier.tasks_digest
                        and context["source_inventory_sha256"] == classifier.source_inventory_digest
                        and context["verifier_source_sha256"] == classifier.verifier_source_digest
                        and context["parent_protocol_sha256"] == parent["protocol_sha256"]
                        and context["quote_namespace"] == "pilot-v2-recovery/" + protocol_hash + "/metadata/history"
                        and context["automatic_retries"] == 0, "R1 raw request/source/identity lineage differs")
                for key in ("model", "provider", "condition_id", "task_id", "root_id", "sample_index", "output_budget_tokens", "request_sha256"):
                    require(context[key] == cell[key], "R1 cell/raw context differs")
                require(load(intent_path) == {"schema_version": 1, "cell": cell, "request_sha256": cell["request_sha256"],
                    "protocol_sha256": protocol_hash, "source_inventory_sha256": classifier.source_inventory_digest},
                    "Pre-reservation R1 logical intent differs")
                quote_path = scope / "metadata/history" / (context["quote_receipt_sha256"] + ".json")
                quote = load(quote_path)
                require(sha(quote_path.read_bytes()) == context["quote_receipt_sha256"]
                        and quote["endpoint"] == "/models/" + GPT + "/endpoints"
                        and quote["response"]["http_status"] == 200 and not quote["response"].get("json", {}).get("error"),
                        "R1 pinned quotation differs")
                A.check_capture(quote["response"])
                price = runtime["ceiling_rates"](quote["response"], "AkashML")
                require(price == (Decimal(context["quoted_prompt_rub_per_token"]), Decimal(context["quoted_completion_rub_per_token"]))
                        and runtime["estimate"](request, price) == Decimal(context["reservation_rub"]), "R1 conservative reservation differs")
                cost_path = scope / "cost-plans" / (context["cost_plan_sha256"] + ".json")
                cost_plan = load(cost_path)
                quoted = [row for row in cost_plan["cells"] if row["call_id"] == cell["call_id"]]
                require(sha(cost_path.read_bytes()) == context["cost_plan_sha256"] and len(cost_plan["cells"]) == 96
                        and len(quoted) == 1 and {row["call_id"] for row in cost_plan["cells"]} == new_ids
                        and quoted[0]["reservation_rub"] == context["reservation_rub"]
                        and quoted[0]["quote_receipt_sha256"] == context["quote_receipt_sha256"]
                        and cost_plan["full_roster_fits_stage_budget"] is True
                        and cost_plan["protocol_sha256"] == protocol_hash
                        and cost_plan["source_inventory_sha256"] == classifier.source_inventory_digest
                        and cost_plan["dispatch_plan_sha256"] == results["dispatch_plan_sha256"], "Full new96 preflight binding differs")
                result = {**result, "reused_record_without_resend": record.get("reused_record_without_resend", False)}
                classifier.paid_cell = lambda ignored, result=result: result
                replayed = classifier.execute_cell(cell)
                require(replayed == record, "Frozen R1 physical grading/status/censor replay differs")
                trace = load(directory / "trace.json")
                require({k: v for k, v in trace.items() if k != "reused_record_without_resend"} ==
                        {k: v for k, v in replayed.items() if k != "reused_record_without_resend"}, "R1 first physical trace differs")
                require(record["phase"] == "pilot_v2_stage_A" and record["protocol_sha256"] == protocol_hash,
                        "Legacy physical phase is not explicitly bound to R1")
                regenerated.append(replayed)
                legacy_phase_count += 1
                finalized.append(cell["call_id"])
                referenced.add(context["reservation_id"])
            else:
                reserved, intended = (directory / "reservation.json").is_file(), intent_path.is_file()
                expected = "unresolved_attempt" if reserved else "unresolved_intent" if intended else "not_dispatched"
                require(record["phase"] == PHASE and record["status"] == expected and record.get("correct") is None
                        and record.get("gradable") is False and record.get("text") == ""
                        and record.get("attempted") is (True if reserved else None if intended else False)
                        and all(record.get(key) == value for key, value in cell.items()), "R1 unsent/unknown physical cell differs")
                if reserved:
                    context = load(directory / "reservation.json")
                    require(context["reservation_id"] in ledger and ledger[context["reservation_id"]]["state"] in ("pending", "unknown"),
                            "Unresolved R1 observation lost its reserve")
                    referenced.add(context["reservation_id"])
                (unresolved if reserved or intended else unattempted).append(cell["call_id"])
                regenerated.append(record)
        require(len(referenced) == len(finalized) + sum((state / "calls" / cell_id / "reservation.json").is_file() for cell_id in unresolved)
                and {row["id"] for row in rows[len(launch):]} == referenced, "R1 reserve roster contains duplicates/missing/new unrelated commitments")
        replayed_results = {**results, "records": regenerated}
        results_bytes = runtime["encode"](replayed_results)
        require(results_bytes == (scope / "results.json").read_bytes(), "R1 exact results reconstruction differs")
        support_path = unpacked / "project" / EXPORT.SUPPORT
        support = stats.summarize_support(regenerated, tasks, [row["model"] for row in protocol["models"]],
            output_budgets=tuple(protocol["generation"]["output_budget_tokens"]),
            prefix_budgets=tuple(protocol["measurement"]["observed_prefix_words"]), stage="development_probe")
        if "input_sha256" in load(support_path):
            support["input_sha256"] = {"records": sha(results_bytes), "tasks": classifier.tasks_digest}
        support_bytes = stats.canonical(support) + b"\n"
        require(support_bytes == support_path.read_bytes(), "R1 frozen class-support is not byte-identical")
        (output / "replayed-results.json").write_bytes(results_bytes)
        (output / "replayed-class-support.json").write_bytes(support_bytes)
    return {"condition": "R1", "all_planned_cells": 192, "reused_A_DeepSeek_records_exact": 96,
            "new_GPT_planned_cells": 96, "new_GPT_finalized_calls": len(finalized), "new_GPT_not_dispatched": len(unattempted),
            "new_GPT_unresolved_intents_or_attempts": len(unresolved), "legacy_physical_phase_records_explicit": legacy_phase_count,
            "ledger_rows": len(rows), "closed_A_ledger_rows_exact": len(launch), "charged_or_reserved_rub": str(committed),
            "remaining_to_global_cap_rub": str(Decimal(protocol["budget"]["cap_total_rub"]) - committed),
            "original_stage_ceiling_rub": protocol["budget"]["absolute_stage_ceiling_rub"],
            "budget_within_authorized_caps": committed <= min(Decimal(protocol["budget"]["cap_total_rub"]), Decimal(protocol["budget"]["absolute_stage_ceiling_rub"])),
            "source_files_exact": len(inventory["files"]), "source_inventory_sha256": payload["source_inventory_sha256"],
            "results_exact": True, "results_sha256": sha(results_bytes), "class_support_exact": True,
            "class_support_sha256": sha(support_bytes), "selected_common_output_cap": support["selected_common_output_cap"],
            "entire_fixed_roster_resolved": support["entire_fixed_roster_resolved"],
            "primary_A_preserved": True, "mixed_provenance": True, "independent_roots": 24,
            "bookkeeping_scope": "original cache flags and unsent stop reasons retained; raw presence/unknown states independently checked",
            "scientific_validity": "not_assessed", "E0": "not_passed"}


def reproduce(manifest_path, output):
    manifest_path, output = Path(manifest_path).resolve(strict=True), Path(output).absolute()
    require(not output.exists(), "Choose a new R1 offline output directory")
    os.environ["OPENBLAS_NUM_THREADS"], os.environ["OMP_NUM_THREADS"] = "1", "1"
    started = datetime.now(timezone.utc).isoformat()
    with A.socket_guard() as network:
        EXPORT.verify_recovery(manifest_path)
        output.mkdir(parents=True)
        EXPORT.verify_recovery(manifest_path, output / "unpacked")
        parent_manifest = output / "unpacked/bundle/parent-A/manifest.json"
        parent = A.reproduce(parent_manifest, output / "primary-A")
        require(parent["selected_common_output_cap"] is None and not parent["entire_fixed_roster_resolved"],
                "Original A primary failure has not been preserved")
        result = replay_recovery(output / "unpacked", output, load(manifest_path), output / "primary-A")
        require(not network and parent["network_attempts"] == 0, "R1 replay attempted network access")
    receipt = {"schema_version": 1, "status": "passed", "started_utc": started,
               "finished_utc": datetime.now(timezone.utc).isoformat(), "bundle_manifest_sha256": sha(manifest_path.read_bytes()),
               "primary_A_manifest_sha256": sha(parent_manifest.read_bytes()), "primary_A_replay_status": parent["status"],
               "verification_program_path": "scripts/reproduce_pilot_v2_recovery.py", "verification_program_sha256": sha(Path(__file__).read_bytes()),
               "network_attempts": len(network), **result}
    (output / "reproduction-check.json").write_bytes(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = reproduce(args.manifest, args.output)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        failure = {"status": "failed", "reason": str(exc) if isinstance(exc, (A.ReplayError, EXPORT.A.DeltaError)) else type(exc).__name__,
                   "scientific_validity": "not_assessed"}
        if args.output.exists():
            (args.output / "reproduction-failure.json").write_bytes(encoded(failure))
        print(json.dumps(failure, indent=2))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
