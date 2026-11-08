"""Verify a lossless pilot-v2 delta and replay frozen grading/support offline.

The sealed v1 bundle is referenced by its manifest hash, not copied. This is a
mechanical source/raw-data replay, not independent scientific review or E0.
"""
from __future__ import annotations

import argparse
import ast
import base64
from collections import Counter, defaultdict, deque
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import types


class ReplayError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReplayError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")


def load(path):
    return json.loads(Path(path).read_bytes())


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def socket_guard():
    calls = []
    def denied(*args, **kwargs):
        calls.append("socket_operation_blocked")
        raise ReplayError("Network is disabled during pilot-v2 replay")
    targets = [(socket, "create_connection"), (socket, "getaddrinfo"), (socket, "getnameinfo"),
               (socket.socket, "connect"), (socket.socket, "connect_ex"), (socket.socket, "sendto")]
    previous = [(owner, name, getattr(owner, name)) for owner, name in targets]
    for owner, name in targets:
        setattr(owner, name, denied)
    try:
        yield calls
    finally:
        for owner, name, value in previous:
            setattr(owner, name, value)


def selected_definitions(path, names, globals_):
    """Compile exact frozen definitions, without collector initialization/imports."""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    definitions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    require({node.name for node in definitions} == set(names), "Frozen replay definition is absent")
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), "exec"), globals_)


@contextmanager
def frozen_runtime(source):
    """Use archived task/statistical code and exact selected collector methods.

    Unused paid paths and the historical Stage-0 verifier are never executed.
    No dependency on a currently checked-out scientific source is introduced.
    """
    names = [name for name in sys.modules if name == "pilot_v2" or name.startswith("pilot_v2.")]
    previous = {name: sys.modules.pop(name) for name in names}
    package = types.ModuleType("pilot_v2")
    package.__path__ = [str(source / "pilot_v2")]
    sys.modules["pilot_v2"] = package
    try:
        tasks = module_from(source / "pilot_v2/tasks.py", "pilot_v2.tasks")
        stats = module_from(source / "pilot_v2/statistical_design.py", "pilot_v2.statistical_design")
        traces = module_from(source / "stage0/traces.py", "pilot_v2_replay_frozen_traces")
        namespace = {"json": json, "Decimal": Decimal, "sha": sha, "require": require,
                     "StopRun": ReplayError, "defaultdict": defaultdict, "deque": deque,
                     "inspect_trace": traces.inspect_trace, "KIND": "pilot_v2_generation",
                     "read_json": load}
        selected_definitions(source / "stage0/runner.py", {"encode", "estimate"}, namespace)
        selected_definitions(source / "resumption/runner.py", {"ceiling_rates"}, namespace)
        tree = ast.parse((source / "pilot_v2/runner.py").read_bytes())
        original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PilotV2Runner")
        method_names = {"_make_plan", "body", "execute_cell"}
        methods = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in method_names]
        require({node.name for node in methods} == method_names, "Frozen collector replay methods are absent")
        replay_class = ast.ClassDef(name="FrozenClassifier", bases=[], keywords=[], body=methods, decorator_list=[])
        ast.fix_missing_locations(replay_class)
        selected_definitions(source / "pilot_v2/runner.py", {"corpus_tasks"}, namespace)
        exec(compile(ast.Module(body=[replay_class], type_ignores=[]), str(source / "pilot_v2/runner.py"), "exec"), namespace)
        yield tasks, stats, namespace
    finally:
        for name in list(sys.modules):
            if name == "pilot_v2" or name.startswith("pilot_v2.") or name == "pilot_v2_replay_frozen_traces":
                del sys.modules[name]
        sys.modules.update(previous)


def check_capture(response):
    require("headers" not in response, "Private HTTP headers are not part of portable evidence")
    if "body_base64" in response:
        try:
            body = base64.b64decode(response["body_base64"], validate=True)
        except (ValueError, TypeError):
            raise ReplayError("Malformed captured HTTP body") from None
        require(sha(body) == response["body_sha256"], "Captured body hash differs")
        if response.get("raw_body") is not None:
            require(body.decode("utf-8") == response["raw_body"], "Captured UTF-8 body differs")
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                require(payload == response["json"], "Parsed response differs from captured raw bytes")
        if response.get("body_storage") == "original_bytes":
            require(response.get("received_body_sha256") == sha(body), "Original captured body hash differs")


def check_call(directory, ledger, *, protocol_hash=None):
    request_path, response_path = directory / "request.json", directory / "response.json"
    context, result = load(directory / "reservation.json"), load(directory / "result.json")
    request, response = load(request_path), load(response_path)
    require(context["call_id"] == directory.name and result["call_id"] == directory.name, "Raw call ID differs")
    logical = sha(encoded({"kind": context["kind"], "identity": context["identity"],
                          "protocol": context["protocol_sha256"], "model": context["model"]}))
    require(logical == directory.name, "Raw logical call identity hash differs")
    require(all(result.get(key) == value for key, value in context.items()), "Raw reservation/result context differs")
    require(context["request_sha256"] == sha(request_path.read_bytes()) and result["response_sha256"] == sha(response_path.read_bytes())
            and result["response"] == response and result["http_status"] == response.get("http_status"),
            "Raw request/response/result hashes differ")
    if protocol_hash is not None:
        require(context["protocol_sha256"] == protocol_hash, "Raw call uses a different protocol")
    row = ledger.get(context["reservation_id"])
    require(row is not None and Decimal(row["reservation_rub"]) == Decimal(context["reservation_rub"]),
            "Raw call reservation is absent from shared ledger")
    reservation, commitment = Decimal(row["reservation_rub"]), Decimal(row["charged_or_reserved_rub"])
    require(reservation.is_finite() and reservation > 0 and commitment.is_finite() and commitment >= reservation,
            "Raw call budget commitment was released or is invalid")
    cost = (response.get("json", {}).get("usage") or {}).get("cost")
    if cost is None:
        cost = response.get("json", {}).get("cost")
    if cost is not None:
        try:
            cost = Decimal(str(cost))
            valid = cost.is_finite() and cost >= 0
        except Exception:
            valid = False
        if valid:
            require(row.get("reported_cost_rub") == str(cost) and commitment == max(reservation, cost),
                    "Reported HTTP cost differs from retained commitment")
        else:
            require(row.get("cost_parse_error") is True and commitment == reservation, "Invalid reported cost was not retained conservatively")
    else:
        require(row.get("reported_cost_rub") is None and commitment == reservation, "Missing cost reservation changed")
    require(row["state"] == ("finished" if response.get("http_status") is not None else "unknown"),
            "Transport finalization differs from ledger state")
    check_capture(response)
    return request, response, context, result


def replay_unpacked(unpacked, output, manifest):
    payload = manifest["payload"]
    protocol_hash = payload["protocol_sha256"]
    state, scope = unpacked / "state", unpacked / payload["namespace"]
    require(payload["namespace"] == "state/pilot-v2/" + protocol_hash, "Unsafe pilot-v2 namespace")
    protocol, corpus = load(scope / "protocol.json"), load(scope / "corpus.json")
    inventory, plan, results = (load(scope / name) for name in ("source-inventory.json", "dispatch-plan.json", "results.json"))
    require(sha((scope / "protocol.json").read_bytes()) == protocol_hash and protocol["status"] == "prospective_frozen_development_probe",
            "Frozen protocol binding differs")
    require(protocol["generation"]["output_budget_tokens"] == [2048, 8192]
            and protocol["generation"]["max_calls"] == 192 and protocol["generation"]["automatic_retries"] == 0
            and protocol["measurement"]["allow_budget_censored_gradeable"] is False
            and protocol["measurement"]["embeddings_in_stage_A"] is False
            and Decimal(protocol["budget"]["cap_total_rub"]) == Decimal(3000)
            and Decimal(protocol["budget"]["stage_additional_cap_rub"]) == Decimal(1200),
            "Frozen measurement or authorized budget contract differs")
    require(sha((scope / "source-inventory.json").read_bytes()) == payload["source_inventory_sha256"], "Source inventory binding differs")
    require(sha((scope / "corpus.json").read_bytes()) == protocol["tasks"]["file_sha256"]
            and (unpacked / "project" / protocol["tasks"]["path"]).read_bytes() == (scope / "corpus.json").read_bytes(),
            "Public and bound corpus differ")
    require((unpacked / "project/design/PILOT_V2_PROTOCOL_2026_11_08.json").read_bytes() == (scope / "protocol.json").read_bytes(),
            "Public and bound protocol differ")
    source = scope / "source"
    for name, digest in inventory["files"].items():
        require(sha((source / name).read_bytes()) == digest and (source / name).read_bytes() == (unpacked / "project" / name).read_bytes(),
                "Frozen source bytes differ")
    require({path.relative_to(source).as_posix() for path in source.rglob("*.py")} == set(inventory["files"]),
            "Frozen code closure has unlisted Python sources")
    parent = protocol["parent"]
    require(sha((state / "protocol.json").read_bytes()) == parent["protocol_sha256"]
            and sha((state / "source-inventory.json").read_bytes()) == parent["source_inventory_sha256"]
            and payload["v1_bundle_manifest_sha256"] == parent["v1_raw_bundle_manifest_sha256"], "Parent evidence binding differs")
    for name, digest in load(state / "source-inventory.json")["files"].items():
        require(inventory["files"].get(name) == digest, "Inherited v1 source bytes were substituted")
    for section in ("statistical_plan", "planning_scenarios"):
        if section in protocol:
            artifact = protocol[section]
            require(sha((unpacked / "project" / artifact["path"]).read_bytes()) == artifact["sha256"],
                    "Prospectively bound public design artifact differs")
    launch_path = scope / "ledger-launch.json"
    launch, rows = load(launch_path), load(state / "ledger.json")
    require(sha(launch_path.read_bytes()) == parent["launch_ledger_sha256"] and len(launch) == parent["launch_ledger_rows"]
            and rows[:len(launch)] == launch, "Shared launch ledger prefix changed")
    ledger = {row["id"]: row for row in rows}
    require(len(ledger) == len(rows), "Repeated shared reservation ID")
    amounts = [Decimal(row["charged_or_reserved_rub"]) for row in rows]
    require(all(value.is_finite() and value >= 0 for value in amounts), "Invalid shared ledger commitment")
    committed = sum(amounts, Decimal(0))
    require(sum((Decimal(row["charged_or_reserved_rub"]) for row in launch), Decimal(0)) == Decimal(parent["launch_charged_or_reserved_rub"]),
            "Launch amount differs from frozen parent ledger")
    require(str(committed) == results["charged_or_reserved_rub"], "Results accounting differs from archived shared ledger")
    accepted, unattempted, unresolved, referenced_reservations = [], [], [], set()
    with frozen_runtime(source) as (tasks_module, stats, runtime):
        for spec in protocol["models"]:
            directory = state / "calls" / spec["parent_admission_call_id"]
            request, response, context, _ = check_call(directory, ledger, protocol_hash=parent["protocol_sha256"])
            require(sha((directory / "request.json").read_bytes()) == spec["parent_request_sha256"]
                    and sha((directory / "response.json").read_bytes()) == spec["parent_response_sha256"]
                    and request["model"] == response["json"].get("model") == spec["model"]
                    and response["json"].get("provider") == spec["provider"] and response["http_status"] == 200
                    and request.get("reasoning", {}).get("enabled") is True and request.get("include_reasoning") is True
                    and response["json"].get("error") is None
                    and runtime["inspect_trace"](response["json"])["status"] == "visible_trace_candidate",
                    "Inherited route admission differs")
        tasks, ordered = runtime["corpus_tasks"](corpus)
        stats.validate_probe_layout(tasks)
        classifier = runtime["FrozenClassifier"]()
        classifier.protocol, classifier.protocol_digest = protocol, protocol_hash
        classifier.tasks_digest, classifier.source_inventory_digest = sha((scope / "corpus.json").read_bytes()), payload["source_inventory_sha256"]
        classifier.verifier_source_digest = inventory["files"]["pilot_v2/tasks.py"]
        classifier.task_lookup = {task["task_id"]: task for task in tasks}
        classifier.model_specs = {spec["model"]: spec for spec in protocol["models"]}
        require(runtime["encode"](classifier._make_plan(ordered)) == (scope / "dispatch-plan.json").read_bytes(), "Prospective allocation/body/seed roster differs")
        require(len(results["records"]) == len(plan["cells"]) == 192
                and [row["trace_id"] for row in results["records"]] == [row["call_id"] for row in plan["cells"]],
                "Results do not retain the full ordered planned roster")
        planned_ids = {cell["call_id"] for cell in plan["cells"]}
        require(all(path.stem in planned_ids for path in (scope / "intents").glob("*.json")),
                "An unlisted V2 logical intent is present")
        require({path.name for path in (state / "calls").iterdir() if path.is_dir()} <= planned_ids |
                {spec["parent_admission_call_id"] for spec in protocol["models"]}, "Unlisted raw call directory in delta")
        require(results["dispatch_plan_sha256"] == sha((scope / "dispatch-plan.json").read_bytes())
                and results["protocol_sha256"] == protocol_hash and results["corpus_sha256"] == classifier.tasks_digest
                and results["source_inventory_sha256"] == classifier.source_inventory_digest,
                "Results header binding differs")
        scratch = output / "classifier-scratch"
        classifier.calls, classifier.scope = scratch / "calls", scratch / "scope"
        classifier.fixture_verifier = None
        classifier.locked = nullcontext
        classifier.save = lambda path, document: sha(runtime["encode"](document))
        classifier._route_state = lambda: {"schema_version": 1, "operational_failure_calls": {}}
        regenerated = []
        for cell, record in zip(plan["cells"], results["records"]):
            directory = state / "calls" / cell["call_id"]
            intent_path = scope / "intents" / (cell["call_id"] + ".json")
            if (directory / "result.json").is_file():
                request, response, context, result = check_call(directory, ledger, protocol_hash=protocol_hash)
                require(runtime["encode"](classifier.body(cell)) == (directory / "request.json").read_bytes()
                        and context["kind"] == "pilot_v2_generation" and context["identity"] == [cell["condition_id"], 0]
                        and context["corpus_sha256"] == classifier.tasks_digest
                        and context["source_inventory_sha256"] == classifier.source_inventory_digest
                        and context["verifier_source_sha256"] == classifier.verifier_source_digest
                        and context["parent_protocol_sha256"] == parent["protocol_sha256"]
                        and context["quote_namespace"] == "pilot-v2/" + protocol_hash + "/metadata/history"
                        and context["automatic_retries"] == 0, "V2 raw request/source lineage differs")
                for key in ("model", "provider", "condition_id", "task_id", "root_id", "sample_index", "output_budget_tokens", "request_sha256"):
                    require(context[key] == cell[key], "V2 cell/context binding differs")
                intent = load(intent_path)
                require(intent == {"schema_version": 1, "cell": cell, "request_sha256": cell["request_sha256"],
                                   "protocol_sha256": protocol_hash, "source_inventory_sha256": classifier.source_inventory_digest},
                        "Pre-reservation logical intent differs")
                quote_path = scope / "metadata/history" / (context["quote_receipt_sha256"] + ".json")
                require(sha(quote_path.read_bytes()) == context["quote_receipt_sha256"], "Pinned quote receipt hash differs")
                quote = load(quote_path)
                require(quote["endpoint"] == "/models/" + cell["model"] + "/endpoints"
                        and quote["response"]["http_status"] == 200 and not quote["response"].get("json", {}).get("error"),
                        "Pinned quotation model/status differs")
                check_capture(quote["response"])
                price = runtime["ceiling_rates"](quote["response"], cell["provider"])
                require(price == (Decimal(context["quoted_prompt_rub_per_token"]), Decimal(context["quoted_completion_rub_per_token"]))
                        and runtime["estimate"](request, price) == Decimal(context["reservation_rub"]), "Conservative pinned reservation differs")
                cost_path = scope / "cost-plans" / (context["cost_plan_sha256"] + ".json")
                cost_plan = load(cost_path)
                require(sha(cost_path.read_bytes()) == context["cost_plan_sha256"]
                        and cost_plan["dispatch_plan_sha256"] == results["dispatch_plan_sha256"]
                        and cost_plan["protocol_sha256"] == protocol_hash
                        and cost_plan["source_inventory_sha256"] == classifier.source_inventory_digest
                        and cost_plan["full_roster_fits_stage_budget"] is True, "Full allocation preflight binding differs")
                quoted_cell = [row for row in cost_plan["cells"] if row["call_id"] == cell["call_id"]]
                require(len(cost_plan["cells"]) == 192 and len(quoted_cell) == 1
                        and quoted_cell[0]["reservation_rub"] == context["reservation_rub"]
                        and quoted_cell[0]["quote_receipt_sha256"] == context["quote_receipt_sha256"],
                        "Full allocation preflight reservation differs from dispatched call")
                result = {**result, "reused_record_without_resend": record.get("reused_record_without_resend", False)}
                classifier.paid_cell = lambda ignored, result=result: result
                replayed = classifier.execute_cell(cell)
                require(replayed == record, "Frozen raw grading/status/censor replay differs")
                trace = load(directory / "trace.json")
                require({k: v for k, v in trace.items() if k != "reused_record_without_resend"} ==
                        {k: v for k, v in replayed.items() if k != "reused_record_without_resend"}, "First-observation trace differs")
                regenerated.append(replayed)
                accepted.append(cell["call_id"])
                referenced_reservations.add(context["reservation_id"])
            else:
                # Stopping bookkeeping is retained; never fabricate a raw outcome.
                reserved = (directory / "reservation.json").is_file()
                intended = intent_path.is_file()
                expected = "unresolved_attempt" if reserved else "unresolved_intent" if intended else "not_dispatched"
                require(record["status"] == expected and record.get("correct") is None and record.get("gradable") is False
                        and record.get("text") == "" and record.get("attempted") is (True if reserved else None if intended else False)
                        and all(record.get(key) == value for key, value in cell.items()), "Unsent/unresolved cell is not retained faithfully")
                if reserved:
                    context = load(directory / "reservation.json")
                    require(context["reservation_id"] in ledger and ledger[context["reservation_id"]]["state"] in ("pending", "unknown"),
                            "Unresolved attempt lost its shared reserve")
                    referenced_reservations.add(context["reservation_id"])
                (unresolved if reserved or intended else unattempted).append(cell["call_id"])
                regenerated.append(record)
        require({row["id"] for row in rows[len(launch):]} == referenced_reservations, "Delta ledger rows do not match all retained V2 attempts")
        replayed_document = {**results, "records": regenerated}
        require(runtime["encode"](replayed_document) == (scope / "results.json").read_bytes(), "Exact results reconstruction differs")
        support = stats.summarize_support(regenerated, tasks, [spec["model"] for spec in protocol["models"]],
            output_budgets=tuple(protocol["generation"]["output_budget_tokens"]),
            prefix_budgets=tuple(protocol["measurement"]["observed_prefix_words"]), stage="development_probe")
        support_path = unpacked / "project/artifacts/pilot-v2-2026-11-08/class-support.json"
        original_support = load(support_path)
        if "input_sha256" in original_support:
            support["input_sha256"] = {"records": sha((scope / "results.json").read_bytes()), "tasks": classifier.tasks_digest}
        support_bytes = stats.canonical(support) + b"\n"
        require(support_bytes == support_path.read_bytes(), "Frozen class-support table is not byte-identical")
        (output / "replayed-results.json").write_bytes(runtime["encode"](replayed_document))
        (output / "replayed-class-support.json").write_bytes(support_bytes)
    return {"all_planned_cells": 192, "raw_finalized_calls": len(accepted), "not_dispatched": len(unattempted),
            "unresolved_intents_or_attempts": len(unresolved), "ledger_rows": len(rows), "launch_rows_exact": len(launch),
            "charged_or_reserved_rub": str(committed), "remaining_to_global_cap_rub": str(Decimal(protocol["budget"]["cap_total_rub"]) - committed),
            "budget_within_authorized_caps": committed <= min(Decimal(protocol["budget"]["cap_total_rub"]), Decimal(protocol["budget"]["absolute_stage_ceiling_rub"])),
            "results_sha256": sha((scope / "results.json").read_bytes()), "class_support_sha256": sha(support_bytes),
            "class_support_exact": True, "results_exact": True, "selected_common_output_cap": support["selected_common_output_cap"],
            "entire_fixed_roster_resolved": support["entire_fixed_roster_resolved"],
            "source_inventory_sha256": payload["source_inventory_sha256"], "source_files_exact": len(inventory["files"]),
            "replay_scope": "exact frozen plan/body/classifier methods, task verifier and statistical support; no paid paths executed",
            "bookkeeping_scope": "original cache-reuse flags and unsent stop-reason text retained; raw presence/unknown status independently checked",
            "scientific_validity": "not_assessed", "E0": "not_passed"}


def reproduce(manifest_path, output):
    manifest_path, output = Path(manifest_path).resolve(strict=True), Path(output).absolute()
    require(not output.exists(), "Choose a new offline replay output directory")
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    started = datetime.now(timezone.utc).isoformat()
    exporter = module_from(Path(__file__).with_name("export_pilot_v2.py"), "pilot_v2_delta_exporter")
    with socket_guard() as network:
        exporter.verify_delta(manifest_path)
        output.mkdir(parents=True)
        exporter.verify_delta(manifest_path, output / "unpacked")
        result = replay_unpacked(output / "unpacked", output, load(manifest_path))
        require(not network, "Offline replay attempted a network operation")
    receipt = {"schema_version": 1, "status": "passed", "started_utc": started,
               "finished_utc": datetime.now(timezone.utc).isoformat(), "bundle_manifest_sha256": sha(manifest_path.read_bytes()),
               "verification_program_path": "scripts/reproduce_pilot_v2.py", "verification_program_sha256": sha(Path(__file__).read_bytes()),
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
    except (ReplayError, OSError, ValueError, KeyError) as exc:
        failure = {"status": "failed", "reason": str(exc) if isinstance(exc, ReplayError) else type(exc).__name__,
                   "scientific_validity": "not_assessed"}
        if args.output.exists():
            (args.output / "reproduction-failure.json").write_bytes(encoded(failure))
        print(json.dumps(failure, indent=2))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
