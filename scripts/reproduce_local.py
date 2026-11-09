"""Verify a portable local bundle and rerun the frozen analysis without API access.

Usage:
    python scripts/reproduce_local.py --manifest evidence/BUNDLE/manifest.json \
        --output .research/offline-reproduction

Install requirements-resumption.txt first. The output directory must be new.
The exporter verifies every shard and restores exact original bytes. Semantic
records are reconstructed only for aggregate files that existed at export, using
their vector-free completion inventory and the retained raw embedding responses.
An incomplete or invalid embedding mode is reported as unavailable in its
entirety. No vector, label, completed call or missing result is synthesized.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import gc
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys


MODELS = ("baai/bge-m3", "qwen/qwen3-embedding-8b")
HEX = re.compile(r"^[0-9a-f]{64}$")
COMPAT_RULE = "ascii_casefold_only"
COMPAT_AMENDMENT = "design/LOCAL_EMBEDDING_COMPAT_2026_11_08.json"
COMPAT_COLLECTOR = "scripts/collect_embedding_compat.py"
COMPAT_STATE = "compatibility/embedding-ascii-casefold-v1"
PINNED_AMENDMENT = "design/LOCAL_EMBEDDING_PINNED_2026_11_08.json"
PINNED_COLLECTOR = "scripts/collect_embedding_pinned.py"


class ReproductionError(ValueError):
    pass


def encoded(value):
    """Exact Runner.save JSON encoding, without a trailing newline."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def document_identity(value):
    """Hash large reconstructed JSON incrementally to avoid a second byte copy."""
    digest, count = hashlib.sha256(), 0
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    for piece in encoder.iterencode(value):
        data = piece.encode("utf-8")
        digest.update(data)
        count += len(data)
    return digest.hexdigest(), count


def safe_relative(value):
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise ReproductionError("Unsafe source inventory path")
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or path.as_posix() != value
            or any(part in (".", "..") or ":" in part for part in path.parts)):
        raise ReproductionError("Unsafe source inventory path")
    return path


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReproductionError("Cannot load the declared local module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolves the defining module here.
    spec.loader.exec_module(module)
    return module


def verify_frozen_sources(state):
    inventory_path = state / "source-inventory.json"
    inventory = json_file(inventory_path)
    files = inventory.get("files")
    required = ("resumption/analysis.py", "resumption/generator_audit.py")
    if (not isinstance(files, dict) or any(name not in files for name in required)
            or any(not isinstance(files[name], str) or not HEX.fullmatch(files[name]) for name in required)):
        raise ReproductionError("Frozen analysis/verifier is absent from the source inventory")
    for relative, expected in files.items():
        safe_relative(relative)
        path = state / "source" / relative
        if not path.is_file() or sha(path.read_bytes()) != expected:
            raise ReproductionError("Frozen source differs from its recorded inventory")
    return inventory, sha(inventory_path.read_bytes())


def expected_chunks(text):
    spans = list(re.finditer(r"\S+", text))[:512]
    return [{"text": text[spans[index].start():spans[min(index + 16, len(spans)) - 1].end()],
             "start": spans[index].start(), "end": spans[min(index + 16, len(spans)) - 1].end(),
             "word_start": index, "word_end": min(index + 16, len(spans))}
            for index in range(0, len(spans), 16)]


def verify_execution_compatibility(state, header, model, bindings):
    """Permit only the separately bound, explicitly documented ASCII case fix."""
    execution = header.get("execution_compatibility")
    if execution is None:
        if header.get("identity_rule") is not None:
            raise ReproductionError("Embedding identity rule has no authorized execution amendment")
        return None
    required = {"amendment_path": COMPAT_AMENDMENT, "collector_path": COMPAT_COLLECTOR,
                "model_identity_rule": COMPAT_RULE, "canonical_requested_model": model,
                "returned_model_identity_preserved": True,
                "base_protocol_sha256": bindings["protocol_sha256"],
                "state_binding_path": COMPAT_STATE + "/binding.json"}
    if (not isinstance(execution, dict) or header.get("identity_rule") != COMPAT_RULE
            or execution.get("returned_model_identity_preserved") is not True
            or any(execution.get(key) != value for key, value in required.items())):
        raise ReproductionError("Embedding execution compatibility metadata is incomplete or unsupported")
    project = state.parent / "project"
    amendment_path, collector_path = project / COMPAT_AMENDMENT, project / COMPAT_COLLECTOR
    if (not amendment_path.is_file() or not collector_path.is_file()
            or sha(amendment_path.read_bytes()) != execution.get("amendment_sha256")
            or sha(collector_path.read_bytes()) != execution.get("collector_sha256")):
        raise ReproductionError("Embedding amendment/collector SHA-256 binding is invalid")
    amendment = json_file(amendment_path)
    models = amendment.get("models")
    expected_routes = amendment.get("expected_routes")
    if (type(amendment.get("schema_version")) is not int or amendment.get("schema_version") != 1
            or not isinstance(amendment.get("amendment_id"), str) or not amendment["amendment_id"]
            or amendment.get("base_protocol_sha256") != bindings["protocol_sha256"]
            or amendment.get("script_sha256") != execution["collector_sha256"]
            or amendment.get("model_identity_rule") != COMPAT_RULE
            or not isinstance(models, list) or len(set(models)) != len(models)
            or not set(models) <= set(MODELS) or model not in models):
        raise ReproductionError("Embedding amendment does not authorize this exact canonical model/rule")
    if (not isinstance(expected_routes, dict) or set(expected_routes) != set(models)
            or any(not isinstance(route, dict) or set(route) != {"provider", "dimension"}
                   or not isinstance(route.get("provider"), str) or not route["provider"]
                   or route["provider"].strip() != route["provider"]
                   or type(route.get("dimension")) is not int
                   or not (route["dimension"] == 1024 if name == "baai/bge-m3"
                           else 1 <= route["dimension"] <= 4096)
                   for name, route in expected_routes.items())):
        raise ReproductionError("Embedding amendment has no exact supported provider/dimension roster")
    try:
        created = datetime.fromisoformat(amendment["created_utc"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ReproductionError("Embedding amendment lacks a valid timezone-aware timestamp") from None
    directory = state / COMPAT_STATE
    if (not (directory / "binding.json").is_file()
            or not (directory / "amendment.json").is_file() or not (directory / "collector.py").is_file()
            or (directory / "amendment.json").read_bytes() != amendment_path.read_bytes()
            or (directory / "collector.py").read_bytes() != collector_path.read_bytes()):
        raise ReproductionError("Embedding compatibility state has no exact amendment/collector snapshot")
    binding = json_file(directory / "binding.json")
    expected_binding = {"schema_version": 1, "amendment_id": amendment["amendment_id"],
                        "amendment_sha256": execution["amendment_sha256"],
                        "collector_sha256": execution["collector_sha256"],
                        "base_protocol_sha256": bindings["protocol_sha256"],
                        "source_inventory_sha256": bindings["source_inventory_sha256"],
                        "corpus_sha256": bindings["corpus_sha256"],
                        "results_sha256": sha((state / "results.json").read_bytes()),
                        "results_document_sha256": sha(encoded(json_file(state / "results.json"))),
                        "model_identity_rule": COMPAT_RULE, "models": models,
                        "expected_routes": expected_routes,
                        "amendment_path": COMPAT_AMENDMENT, "collector_path": COMPAT_COLLECTOR,
                        "scientific_validity": "not_assessed"}
    if binding != expected_binding:
        raise ReproductionError("Embedding compatibility state binding differs from the retained evidence")
    return {**execution, "amendment_id": amendment["amendment_id"],
            "created_utc": amendment["created_utc"], "expected_routes": expected_routes}


def model_identity_matches(returned, requested, compatibility):
    if not isinstance(returned, str):
        return False
    if returned == requested:
        return True
    return (compatibility is not None and compatibility.get("model_identity_rule") == COMPAT_RULE
            and returned.isascii() and requested.isascii() and returned.casefold() == requested.casefold())


def verify_pinned_execution(state, header, model, bindings, originals):
    execution = header.get("execution_pinned_condition")
    if not isinstance(execution, dict) or header.get("identity_rule") != COMPAT_RULE:
        raise ReproductionError("Pinned embedding aggregate has no supported execution metadata")
    project = state.parent / "project"
    amendment_path, collector_path = project / PINNED_AMENDMENT, project / PINNED_COLLECTOR
    if not amendment_path.is_file() or not collector_path.is_file():
        raise ReproductionError("Pinned embedding amendment/collector is absent")
    amendment_sha, collector_sha = sha(amendment_path.read_bytes()), sha(collector_path.read_bytes())
    condition = execution.get("condition_sha256")
    directory_name = "embedding-conditions/" + amendment_sha
    required = {"amendment_path": PINNED_AMENDMENT, "amendment_sha256": amendment_sha,
                "collector_path": PINNED_COLLECTOR, "collector_sha256": collector_sha,
                "model_identity_rule": COMPAT_RULE, "canonical_requested_model": model,
                "returned_model_identity_preserved": True,
                "base_protocol_sha256": bindings["protocol_sha256"], "condition_sha256": amendment_sha,
                "state_binding_path": directory_name + "/binding.json",
                "condition_mapping_path": directory_name + "/mapping.json"}
    if (condition != amendment_sha or header.get("measurement_condition_sha256") != amendment_sha
            or execution.get("returned_model_identity_preserved") is not True
            or any(execution.get(key) != value for key, value in required.items())):
        raise ReproductionError("Pinned execution metadata does not match its exact condition artifacts")
    amendment = json_file(amendment_path)
    models, routes = amendment.get("models"), amendment.get("expected_routes")
    if (type(amendment.get("schema_version")) is not int or amendment["schema_version"] != 1
            or not isinstance(amendment.get("amendment_id"), str) or not amendment["amendment_id"]
            or amendment.get("base_protocol_sha256") != bindings["protocol_sha256"]
            or amendment.get("script_sha256") != collector_sha
            or amendment.get("model_identity_rule") != COMPAT_RULE
            or not isinstance(models, list) or len(set(models)) != len(models)
            or not set(models) <= set(MODELS) or model not in models
            or not isinstance(routes, dict) or set(routes) != set(models)):
        raise ReproductionError("Pinned amendment does not authorize the exact model/condition")
    for name, route in routes.items():
        if (not isinstance(route, dict) or set(route) != {"provider", "dimension"}
                or not isinstance(route.get("provider"), str) or not route["provider"]
                or route["provider"].strip() != route["provider"]
                or type(route.get("dimension")) is not int
                or not (route["dimension"] == 1024 if name == MODELS[0] else 1 <= route["dimension"] <= 4096)):
            raise ReproductionError("Pinned amendment has an unsupported provider/dimension roster")
    parents, replacements = amendment.get("parent_call_ids"), amendment.get("allowed_replacement_call_ids")
    if (any(not isinstance(values, list) or len(set(values)) != len(values)
            or any(not isinstance(value, str) or not HEX.fullmatch(value) for value in values)
            for values in (parents, replacements)) or not set(replacements) <= set(parents)):
        raise ReproductionError("Pinned amendment has invalid parent/replacement call identities")
    try:
        if datetime.fromisoformat(amendment["created_utc"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ReproductionError("Pinned amendment lacks a timezone-aware timestamp") from None
    directory = state / directory_name
    if (not (directory / "binding.json").is_file() or not (directory / "mapping.json").is_file()
            or not (directory / "amendment.json").is_file() or not (directory / "collector.py").is_file()
            or (directory / "amendment.json").read_bytes() != amendment_path.read_bytes()
            or (directory / "collector.py").read_bytes() != collector_path.read_bytes()):
        raise ReproductionError("Pinned state has no exact amendment/collector/mapping snapshot")
    expected_binding = {"schema_version": 1, "amendment_id": amendment["amendment_id"],
                        "amendment_sha256": amendment_sha, "collector_sha256": collector_sha,
                        "base_protocol_sha256": bindings["protocol_sha256"],
                        "source_inventory_sha256": bindings["source_inventory_sha256"],
                        "corpus_sha256": bindings["corpus_sha256"],
                        "results_sha256": sha((state / "results.json").read_bytes()),
                        "results_document_sha256": sha(encoded(json_file(state / "results.json"))),
                        "model_identity_rule": COMPAT_RULE, "models": models, "expected_routes": routes,
                        "parent_call_ids": parents, "allowed_replacement_call_ids": replacements,
                        "condition_sha256": condition, "amendment_path": PINNED_AMENDMENT,
                        "collector_path": PINNED_COLLECTOR, "scientific_validity": "not_assessed"}
    if json_file(directory / "binding.json") != expected_binding:
        raise ReproductionError("Pinned state binding differs from the retained source/results/condition")
    completed = [row["trace_id"] for row in originals if row.get("status") == "completed"]
    expected_mapping = {"schema_version": 1, "condition_sha256": condition,
                        "trace_mapping": {condition + ":" + trace: trace for trace in completed}}
    if json_file(directory / "mapping.json") != expected_mapping:
        raise ReproductionError("Pinned trace mapping changes the original completed-trace population")
    if (execution.get("provider") != routes[model]["provider"]
            or execution.get("dimension") != routes[model]["dimension"]
            or execution.get("parent_call_ids") != parents
            or execution.get("allowed_replacement_call_ids") != replacements):
        raise ReproductionError("Pinned aggregate route/parents differ from the prospective amendment")
    return {**execution, "amendment_id": amendment["amendment_id"],
            "created_utc": amendment["created_utc"], "expected_routes": routes,
            "trace_mapping": expected_mapping["trace_mapping"], "directory_name": directory_name}


def raw_embedding_batch(state, call_id, bindings):
    directory = state / "calls" / call_id
    names = ("reservation", "request", "response", "result")
    if not all((directory / (name + ".json")).is_file() for name in names):
        raise ReproductionError("Selected pinned batch lacks finalized raw evidence")
    raw = {name: (directory / (name + ".json")).read_bytes() for name in names}
    reservation, request, response, result = (json.loads(raw[name]) for name in names)
    identities, model = reservation.get("identity"), reservation.get("model")
    if (reservation.get("kind") != "embedding" or reservation.get("call_id") != call_id
            or model not in MODELS or not isinstance(identities, list) or not identities
            or any(not isinstance(identity, list) or len(identity) != 3 or not isinstance(identity[0], str)
                   or type(identity[1]) is not int or type(identity[2]) is not int for identity in identities)):
        raise ReproductionError("Pinned raw batch has invalid logical chunk identities")
    expected_id = sha(encoded({"kind": "embedding", "identity": identities,
                              "protocol": bindings["protocol_sha256"], "model": model}))
    if (call_id != expected_id or any(reservation.get(key) != value for key, value in bindings.items())
            or sha(raw["request"]) != reservation.get("request_sha256")
            or sha(raw["response"]) != result.get("response_sha256")
            or any(result.get(key) != value for key, value in reservation.items())
            or result.get("response") != response or request.get("model") != model):
        raise ReproductionError("Pinned raw request/response/source binding mismatch")
    inputs, payload = request.get("input"), response.get("json")
    if (not isinstance(inputs, list) or len(inputs) != len(identities)
            or any(not isinstance(text, str) for text in inputs)
            or result.get("http_status") != 200 or response.get("http_status") != 200
            or not isinstance(payload, dict) or payload.get("error") is not None):
        raise ReproductionError("Pinned parent or selected batch has an unknown/invalid HTTP/API result")
    return {"call_id": call_id, "reservation": reservation, "request": request, "response": response,
            "result": result, "identities": identities, "model": model,
            "request_sha256": sha(raw["request"]), "response_sha256": sha(raw["response"]),
            "payload": payload, "inputs": inputs}


def pinned_embedding_calls(state, model, records, marker_rows, policy, bindings, route):
    originals = {row["trace_id"]: row for row in records}
    chunks = {(trace, chunk["start"], chunk["end"]): chunk
              for trace, row in originals.items() if row.get("status") == "completed"
              for chunk in expected_chunks(row["text"])}
    condition, provider = policy["condition_sha256"], policy["provider"]
    references = {}
    for entry in marker_rows:
        record = entry["record"]
        for segment in record.get("embeddings", {}).get(model, []):
            call_id = segment.get("embedding_call_id")
            if (not isinstance(call_id, str) or not HEX.fullmatch(call_id)
                    or segment.get("measurement_condition_sha256") != condition):
                raise ReproductionError("Pinned segment has no exact condition/call binding")
            references.setdefault(call_id, []).append((record["trace_id"], segment))
    if not references:
        raise ReproductionError("Pinned aggregate has no recorded accepted chunks")
    # Resolve all namespaces from preserved sidecars, including other conditions,
    # so a prior unknown attempt cannot disappear by changing its condition ID.
    mapping = {trace: trace for trace in originals}
    for mapping_path in sorted((state / "embedding-conditions").glob("*/mapping.json")):
        declared = json_file(mapping_path)
        if (not HEX.fullmatch(mapping_path.parent.name)
                or declared.get("condition_sha256") != mapping_path.parent.name):
            raise ReproductionError("A condition mapping differs from its namespace directory")
        for paid, original in declared.get("trace_mapping", {}).items():
            if original not in originals or paid != declared.get("condition_sha256", "") + ":" + original:
                raise ReproductionError("A preserved condition mapping has an invalid original trace identity")
            if paid in mapping and mapping[paid] != original:
                raise ReproductionError("Condition mappings disagree about an original trace")
            mapping[paid] = original
    input_texts = {chunk["text"] for chunk in chunks.values()}
    for request_path in sorted((state / "calls").glob("*/request.json")):
        request = json_file(request_path)
        if (request.get("model") == model and isinstance(request.get("input"), list)
                and not (request_path.parent / "reservation.json").is_file()
                and input_texts.intersection(request["input"])):
            raise ReproductionError("An unresolved embedding request lacks a reservation identity")
    for reservation_path in sorted((state / "calls").glob("*/reservation.json")):
        reservation = json_file(reservation_path)
        if reservation.get("kind") != "embedding" or reservation.get("model") != model:
            continue
        identities = reservation.get("identity", [])
        if (not isinstance(identities, list) or any(not isinstance(identity, list) or len(identity) != 3
                or identity[0] not in mapping for identity in identities)):
            raise ReproductionError("An embedding attempt has no preserved original-trace mapping")
        related = any((mapping[identity[0]], identity[1], identity[2]) in chunks for identity in identities)
        if related:
            if any(reservation.get(key) != value for key, value in bindings.items()):
                raise ReproductionError("An underlying embedding attempt uses different bound research inputs")
            result_path, response_path = reservation_path.parent / "result.json", reservation_path.parent / "response.json"
            if (not result_path.is_file() or not response_path.is_file()
                    or json_file(result_path).get("http_status") is None
                    or json_file(response_path).get("http_status") is None
                    or json_file(response_path).get("network_error")):
                raise ReproductionError("An unknown underlying chunk remains in the all-condition journal")
            current = all(identity[0].startswith(condition + ":") for identity in identities)
            if not current and reservation_path.parent.name not in policy["parent_call_ids"]:
                raise ReproductionError("A prior embedding condition was not declared as a parent")
    parent_batches = {call: raw_embedding_batch(state, call, bindings) for call in policy["parent_call_ids"]}
    replacement_keys = {}
    for call in policy["allowed_replacement_call_ids"]:
        parent = parent_batches[call]
        payload, expected = parent["payload"], policy["expected_routes"][parent["model"]]
        items = payload.get("data", [])
        dimension = len(items[0].get("embedding", [])) if items and isinstance(items[0], dict) else None
        if (model_identity_matches(payload.get("model"), parent["model"], policy)
                and payload.get("provider") == expected["provider"] and dimension == expected["dimension"]):
            raise ReproductionError("A replacement parent already satisfies the authorized identity/route")
        keys = set()
        for identity in parent["identities"]:
            if identity[0] not in mapping:
                raise ReproductionError("Rejected parent has no original-trace mapping")
            keys.add((mapping[identity[0]], identity[1], identity[2]))
        replacement_keys[call] = (parent["model"], keys)
    if (route.get("model") != model or route.get("provider") != provider
            or route.get("dimension") != policy["dimension"]
            or route.get("condition_sha256") != condition
            or route.get("amendment_sha256") != policy["amendment_sha256"]
            or route.get("collector_sha256") != policy["collector_sha256"]
            or route.get("identity_rule") != COMPAT_RULE or route.get("provider_identity_verified") is not True):
        raise ReproductionError("Pinned aggregate route is not bound to its exact condition")
    route_path = state / policy["directory_name"] / (model.replace("/", "_") + "-embedding-route.json")
    if not route_path.is_file() or json_file(route_path) != route:
        raise ReproductionError("Pinned aggregate route differs from the retained condition route")
    vectors, responses, returned_models, reused, reused_chunks = {}, set(), set(), 0, 0
    for call_id, selected in sorted(references.items()):
        batch = raw_embedding_batch(state, call_id, bindings)
        if batch["model"] != model:
            raise ReproductionError("Pinned aggregate references another requested model")
        payload = batch["payload"]
        if (not model_identity_matches(payload.get("model"), model, policy)
                or payload.get("provider") != provider):
            raise ReproductionError("Selected pinned batch has an unauthorized returned model/provider")
        items = payload.get("data")
        if (not isinstance(items, list) or len(items) != len(batch["identities"])
                or any(not isinstance(item, dict) or type(item.get("index")) is not int for item in items)
                or sorted(item["index"] for item in items) != list(range(len(items)))):
            raise ReproductionError("Selected pinned batch indices are malformed")
        if any(not isinstance(item.get("embedding"), list) or len(item["embedding"]) != policy["dimension"]
               or any(type(value) not in (int, float) or not math.isfinite(value) for value in item["embedding"])
               or not any(item["embedding"]) for item in items):
            raise ReproductionError("Selected pinned batch has an invalid vector/dimension")
        receipt_name = "calls/" + call_id + "/embedding-pinned-" + condition + ".json"
        receipt_path = state / receipt_name
        if not receipt_path.is_file():
            raise ReproductionError("Selected pinned batch has no condition acceptance receipt")
        receipt = json_file(receipt_path)
        old = receipt.get("accepted_source") == "reused_known_valid_unpinned"
        if old:
            if call_id not in parent_batches or call_id in replacement_keys or batch["request"].get("provider") is not None:
                raise ReproductionError("A reused unpinned batch is not an authorized valid parent")
            reused += 1
        elif (receipt.get("accepted_source") != "condition_request"
              or batch["request"].get("provider") != {"order": [provider], "allow_fallbacks": False}):
            raise ReproductionError("A new condition request does not pin the exact provider without fallback")
        input_mapping, keys = [], set()
        by_key = {}
        for item in items:
            index = item["index"]
            paid, start, end = batch["identities"][index]
            if paid not in mapping:
                raise ReproductionError("Selected pinned chunk lacks its original mapping")
            original = mapping[paid]
            if paid != (original if old else condition + ":" + original):
                raise ReproductionError("Selected pinned chunk uses another measurement condition identity")
            key = (original, start, end)
            if key not in chunks or batch["inputs"][index] != chunks[key]["text"] or key in keys:
                raise ReproductionError("Selected pinned chunk repeats or changes an original observed input")
            keys.add(key)
            input_hash = sha(batch["inputs"][index].encode("utf-8"))
            input_mapping.append({"response_index": index, "original_trace_id": original,
                                  "paid_trace_id": paid, "start": start, "end": end, "input_sha256": input_hash})
            by_key[key] = {"vector": item["embedding"], "provider": provider,
                           "request_sha256": batch["request_sha256"], "response_sha256": batch["response_sha256"],
                           "input_sha256": input_hash, "returned_model_id": payload["model"]}
        input_mapping.sort(key=lambda value: value["response_index"])
        rejected = sorted(call for call, (parent_model, parent_keys) in replacement_keys.items()
                          if parent_model == model and parent_keys & keys)
        if not old:
            intent_path = state / policy["directory_name"] / "intents" / (call_id + ".json")
            expected_intent = {"schema_version": 1, "condition_sha256": condition, "model": model,
                               "original_identity": [[mapping[identity[0]], identity[1], identity[2]]
                                                     for identity in batch["identities"]],
                               "paid_identity": batch["identities"],
                               "request_body_sha256": sha(encoded(batch["request"])),
                               "amendment_sha256": condition}
            if not intent_path.is_file() or json_file(intent_path) != expected_intent:
                raise ReproductionError("A pinned paid batch has no exact prospective original/paid intent")
        expected_receipt = {"schema_version": 1, "condition_sha256": condition, "call_id": call_id,
                            "request_sha256": batch["request_sha256"], "response_sha256": batch["response_sha256"],
                            "requested_model": model, "returned_model_id": payload["model"],
                            "provider": provider, "dimension": policy["dimension"], "identity_rule": COMPAT_RULE,
                            "amendment_sha256": policy["amendment_sha256"], "collector_sha256": policy["collector_sha256"],
                            "accepted_source": "reused_known_valid_unpinned" if old else "condition_request",
                            "input_mapping": input_mapping, "parent_rejected_call_ids": rejected,
                            "body_provider_pinned": not old, "scientific_validity": "not_assessed"}
        if receipt != expected_receipt:
            raise ReproductionError("Pinned acceptance receipt differs from exact batch/mapping/parents")
        selected_keys = set()
        for original, segment in selected:
            key = (original, segment["start"], segment["end"])
            expected_paid = original if old else condition + ":" + original
            chunk_rejections = sorted(call for call, (parent_model, parent_keys) in replacement_keys.items()
                                      if parent_model == model and key in parent_keys)
            if (key not in by_key or key in selected_keys or key in vectors
                    or segment.get("paid_trace_id") != expected_paid
                    or segment.get("pinned_receipt_path") != receipt_name
                    or segment.get("reused_known_valid") is not old
                    or segment.get("request_route_pinned") is not (not old)
                    or segment.get("parent_rejected_call_ids") != chunk_rejections):
                raise ReproductionError("Pinned segment provenance differs from its accepted batch receipt")
            selected_keys.add(key)
            vectors[key] = by_key[key]
            reused_chunks += old
        if selected_keys != keys:
            raise ReproductionError("Pinned aggregate omits part of an accepted raw batch")
        responses.add(batch["response_sha256"])
        returned_models.add(payload["model"])
    first_key = next(iter(chunks), None)
    if (route.get("first_response_sha256") not in responses or first_key not in vectors
            or route.get("first_response_sha256") != vectors[first_key]["response_sha256"]):
        raise ReproductionError("Pinned route's first response is absent from accepted evidence")
    return vectors, {"batches": len(references), "chunks": len(vectors), "route": route,
                     "requested_model": model, "returned_model_ids": sorted(returned_models),
                     "reused_known_valid_batches": reused, "reused_known_chunks": reused_chunks,
                     "new_condition_chunks": len(vectors) - reused_chunks,
                     "parent_calls_retained": policy["parent_call_ids"],
                     "known_rejected_parent_calls_retained": policy["allowed_replacement_call_ids"]}


def embedding_calls(state, model, records, bindings, compatibility=None):
    """Validate whole batches and return their exact vectors by original chunk ID."""
    originals = {row["trace_id"]: row for row in records}
    if len(originals) != len(records):
        raise ReproductionError("Original results contain duplicate trace identities")
    chunks = {}
    for trace_id, row in originals.items():
        if row.get("status") == "completed":
            for chunk in expected_chunks(row["text"]):
                chunks[(trace_id, chunk["start"], chunk["end"])] = chunk
    route_path = state / (model.replace("/", "_") + "-embedding-route.json")
    if not route_path.is_file():
        raise ReproductionError("Completed embedding mode has no bound route")
    route = json_file(route_path)
    if route.get("model") != model:
        raise ReproductionError("Embedding route model differs from the requested mode")
    if compatibility is not None and any(route.get(key) != value for key, value in
            (("identity_rule", COMPAT_RULE), ("amendment_sha256", compatibility["amendment_sha256"]),
             ("collector_sha256", compatibility["collector_sha256"]), ("provider_identity_verified", True))):
        raise ReproductionError("Embedding compatibility route is not bound to the amendment/collector")
    if compatibility is not None and any(route.get(key) != value for key, value in
            compatibility["expected_routes"][model].items()):
        raise ReproductionError("Embedding state route differs from its prospective expected route")
    vectors, batch_count, response_hashes, returned_models = {}, 0, set(), set()
    for reservation_path in sorted((state / "calls").glob("*/reservation.json")):
        reservation = json_file(reservation_path)
        if reservation.get("kind") != "embedding" or reservation.get("model") != model:
            continue
        directory = reservation_path.parent
        call_id = reservation.get("call_id")
        if not isinstance(call_id, str) or not HEX.fullmatch(call_id) or directory.name != call_id:
            raise ReproductionError("Embedding call identity does not match its directory")
        identity = reservation.get("identity")
        if not isinstance(identity, list) or not identity:
            raise ReproductionError("Embedding batch lacks original chunk identities")
        for value in identity:
            if (not isinstance(value, list) or len(value) != 3 or not isinstance(value[0], str)
                    or type(value[1]) is not int or type(value[2]) is not int):
                raise ReproductionError("Embedding chunk identity is malformed")
        expected_call = sha(encoded({"kind": "embedding", "identity": identity,
                                    "protocol": bindings["protocol_sha256"], "model": model}))
        if call_id != expected_call:
            raise ReproductionError("Embedding logical call hash is inconsistent")
        for key, expected in bindings.items():
            if reservation.get(key) != expected:
                raise ReproductionError("Embedding call is bound to different source data")
        paths = {name: directory / (name + ".json") for name in ("request", "response", "result")}
        if not all(path.is_file() for path in paths.values()):
            raise ReproductionError("Embedding attempt has no finalized raw request/response/result")
        raw = {name: path.read_bytes() for name, path in paths.items()}
        request, response, result = (json.loads(raw[name]) for name in ("request", "response", "result"))
        if sha(raw["request"]) != reservation.get("request_sha256"):
            raise ReproductionError("Original embedding request SHA-256 mismatch")
        if (result.get("response_sha256") != sha(raw["response"])
                or any(result.get(key) != value for key, value in reservation.items())
                or result.get("response") != response):
            raise ReproductionError("Original embedding response/result binding mismatch")
        if request.get("model") != model or not isinstance(request.get("input"), list):
            raise ReproductionError("Embedding request model/input is invalid")
        inputs = request["input"]
        if len(inputs) != len(identity) or any(not isinstance(text, str) for text in inputs):
            raise ReproductionError("Embedding request inputs do not match its chunk identities")
        payload = response.get("json")
        if (response.get("http_status") != 200 or result.get("http_status") != 200
                or not isinstance(payload, dict) or payload.get("error") is not None
                or not model_identity_matches(payload.get("model"), model, compatibility)):
            raise ReproductionError("Embedding batch has invalid HTTP/API/model status")
        returned_models.add(payload["model"])
        provider = payload.get("provider")
        provider = provider if isinstance(provider, str) and provider.strip() else None
        if compatibility is not None and provider is None:
            raise ReproductionError("Embedding compatibility requires an explicit returned provider")
        items = payload.get("data")
        if (not isinstance(items, list) or len(items) != len(identity)
                or any(not isinstance(item, dict) or type(item.get("index")) is not int for item in items)
                or sorted(item["index"] for item in items) != list(range(len(identity)))):
            raise ReproductionError("Embedding batch indices are missing or duplicated")
        dimensions = set()
        for item in items:
            vector = item.get("embedding")
            if (not isinstance(vector, list) or not vector
                    or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
                    or not any(vector)):
                raise ReproductionError("Embedding batch contains an invalid or zero vector")
            dimensions.add(len(vector))
        if len(dimensions) != 1:
            raise ReproductionError("Embedding dimensions differ within one batch")
        dimension = next(iter(dimensions))
        if not (dimension == 1024 if model == "baai/bge-m3" else 1 <= dimension <= 4096):
            raise ReproductionError("Embedding dimension violates the model contract")
        if compatibility is not None and compatibility["expected_routes"][model] != {
                "provider": provider, "dimension": dimension}:
            raise ReproductionError("Embedding raw response differs from its prospective expected route")
        if any(route.get(key) != value for key, value in
               (("model", model), ("provider", provider), ("dimension", dimension))):
            raise ReproductionError("Embedding provider/dimension route drift")
        response_hash = sha(raw["response"])
        if compatibility is not None:
            receipt_path = directory / "embedding-compatibility.json"
            if not receipt_path.is_file():
                raise ReproductionError("Embedding batch has no bound compatibility acceptance receipt")
            receipt = json_file(receipt_path)
            expected_receipt = {"schema_version": 1, "call_id": call_id, "requested_model": model,
                                "returned_model_id": payload["model"], "provider": provider,
                                "dimension": dimension, "identity_rule": COMPAT_RULE,
                                "request_sha256": sha(raw["request"]), "response_sha256": response_hash,
                                "amendment_sha256": compatibility["amendment_sha256"],
                                "collector_sha256": compatibility["collector_sha256"],
                                "scientific_validity": "not_assessed"}
            if (type(receipt.get("cached_without_resend")) is not bool
                    or {key: value for key, value in receipt.items() if key != "cached_without_resend"} != expected_receipt):
                raise ReproductionError("Embedding compatibility receipt differs from its raw batch evidence")
        response_hashes.add(response_hash)
        for item in items:
            index = item["index"]
            key = tuple(identity[index])
            if key in vectors or key not in chunks or inputs[index] != chunks[key]["text"]:
                raise ReproductionError("Embedding chunk is repeated, absent, or has changed text")
            vectors[key] = {"vector": item["embedding"], "provider": provider,
                            "request_sha256": sha(raw["request"]), "response_sha256": response_hash,
                            "input_sha256": sha(inputs[index].encode("utf-8")),
                            "returned_model_id": payload["model"]}
        batch_count += 1
    if not vectors or route.get("first_response_sha256") not in response_hashes:
        raise ReproductionError("Completed embedding route has no matching original responses")
    return vectors, {"batches": batch_count, "chunks": len(vectors), "route": route,
                     "requested_model": model, "returned_model_ids": sorted(returned_models)}


def reconstruct_embedding(state, marker, originals, bindings):
    """Restore one completed aggregate exactly, validating every recorded slot."""
    if marker.get("file_present") is not True:
        raise ReproductionError("Embedding aggregate was absent or unfinished at export")
    header = marker.get("header")
    if not isinstance(header, dict) or header.get("embedding_model") not in MODELS:
        raise ReproductionError("Embedding completion header is invalid")
    model = header["embedding_model"]
    if (marker.get("path") != "state/" + model.replace("/", "_") + "-embedded.json"
            or header.get("protocol_sha256") != bindings["protocol_sha256"]
            or header.get("word_chunk_size") != 16 or header.get("max_observed_words") != 512):
        raise ReproductionError("Embedding completion header uses another protocol or chunking")
    pinned = None
    if "execution_pinned_condition" in header:
        if "execution_compatibility" in header:
            raise ReproductionError("Embedding aggregate mixes two execution amendments")
        pinned = verify_pinned_execution(state, header, model, bindings, originals)
        compatibility = pinned
    else:
        compatibility = verify_execution_compatibility(state, header, model, bindings)
    rows = marker.get("records")
    order = marker.get("record_order")
    if not isinstance(rows, list) or not isinstance(order, list):
        raise ReproductionError("Embedding completion inventory has no record order")
    lookup = {row["trace_id"]: row for row in originals}
    if len(lookup) != len(originals) or len(order) != len(lookup) or set(order) != set(lookup):
        raise ReproductionError("Embedding aggregate and original results have different records")
    if [row.get("record", {}).get("trace_id") for row in rows] != order:
        raise ReproductionError("Embedding completion record order is inconsistent")
    needed = {slot.get("model") for row in rows for slot in row.get("vector_slots", [])}
    if not needed or not needed <= set(MODELS):
        raise ReproductionError("Embedding inventory requests an unsupported or absent model")
    maps, audits = {}, {}
    for needed_model in sorted(needed):
        if compatibility is not None and needed_model != model:
            raise ReproductionError("Compatibility aggregate must contain only its canonical requested embedder")
        if pinned is not None:
            maps[needed_model], audits[needed_model] = pinned_embedding_calls(
                state, needed_model, originals, rows, pinned, bindings, header.get("embedding_route", {}))
        else:
            maps[needed_model], audits[needed_model] = embedding_calls(
                state, needed_model, originals, bindings, compatibility)
    restored = []
    seen_slots = set()
    for row in rows:
        record = copy.deepcopy(row["record"])
        trace_id = record["trace_id"]
        base = {key: value for key, value in record.items() if key != "embeddings"}
        original = {key: value for key, value in lookup[trace_id].items() if key != "embeddings"}
        if base != original:
            raise ReproductionError("Embedding aggregate changed an original result record")
        actual_slots = set()
        for slot in row.get("vector_slots", []):
            slot_model, index = slot.get("model"), slot.get("segment_index")
            if type(index) is not int or index < 0 or slot.get("present") is not True:
                raise ReproductionError("Completed embedding aggregate contains an empty vector slot")
            segments = record.get("embeddings", {}).get(slot_model)
            if not isinstance(segments, list) or index >= len(segments):
                raise ReproductionError("Embedding vector slot has no segment")
            segment = segments[index]
            key = (trace_id, segment.get("start"), segment.get("end"))
            slot_id = (slot_model, *key)
            if slot_id in seen_slots:
                raise ReproductionError("Embedding completion inventory repeats a vector slot")
            seen_slots.add(slot_id)
            actual_slots.add((slot_model, index))
            found = maps[slot_model].get(key)
            if found is None:
                raise ReproductionError("Completed aggregate references an absent original vector")
            vector = found["vector"]
            if (slot.get("dimension") != len(vector) or slot.get("vector_sha256") != sha(encoded(vector))
                    or "vector" in segment or segment.get("model_id") != slot_model
                    or segment.get("identity_verified") is not True
                    or segment.get("provider_identity_verified") is not (found["provider"] is not None)
                    or any(segment.get(key) != value for key, value in found.items()
                           if key not in ("vector", "returned_model_id"))
                    or segment.get("text") != lookup[trace_id]["text"][segment["start"]:segment["end"]]):
                raise ReproductionError("Recorded embedding vector/hash/metadata differs from raw evidence")
            if compatibility is not None and (segment.get("identity_rule") != COMPAT_RULE
                    or segment.get("returned_model_id") != found["returned_model_id"]):
                raise ReproductionError("Compatibility segment does not preserve the exact returned model identity")
            if (compatibility is None and "returned_model_id" in segment
                    and segment["returned_model_id"] != found["returned_model_id"]):
                raise ReproductionError("Recorded returned model identity differs from the original response")
            segment["vector"] = vector
        expected_slots = {(embedder, index) for embedder, segments in record.get("embeddings", {}).items()
                          for index in range(len(segments))}
        if actual_slots != expected_slots:
            raise ReproductionError("Not every embedding segment has one recorded vector slot")
        if record.get("status") == "completed":
            segments = record.get("embeddings", {}).get(model)
            chunks = expected_chunks(record["text"])
            if not isinstance(segments, list) or len(segments) != len(chunks) or any(
                    any(segment.get(key) != value for key, value in chunk.items())
                    for segment, chunk in zip(segments, chunks)):
                raise ReproductionError("Embedding aggregate does not cover all exact observed chunks")
        restored.append(record)
    document = {**header, "records": restored}
    digest, count = document_identity(document)
    if digest != marker.get("original_sha256") or count != marker.get("original_bytes"):
        raise ReproductionError("Reconstructed embedding aggregate differs from its original SHA-256/size")
    if header.get("embedding_route") != audits[model]["route"]:
        raise ReproductionError("Aggregate embedding route differs from its bound state route")
    if pinned is not None and any(header.get(key) != audits[model][key]
                                 for key in ("reused_known_chunks", "new_condition_chunks")):
        raise ReproductionError("Pinned aggregate chunk counts differ from selected raw evidence")
    return restored, {"status": "reconstructed_exact", "model": model,
                      "original_sha256": digest, "original_bytes": count,
                      "records": len(restored), "validated_modes": audits,
                      "execution_compatibility": compatibility if pinned is None else None,
                      "execution_pinned_condition": pinned}


def run_analysis(analysis, records, output, budgets, bootstrap_samples=2000,
                 embedder=None, matched_records=None, matched_embedder=None):
    result = analysis.run_analysis(records, budgets, embedder, bootstrap_samples, True,
                                   matched_records, matched_embedder)
    result["admission_smoke_override"] = False
    output.write_bytes(analysis.canonical(result) + b"\n")
    return {"path": output.name, "sha256": sha(output.read_bytes()),
            "analysis_version": result["analysis_version"], "record_digest": result["record_digest"],
            "representation": result["representation"], "embedding_model": result["embedding_model"],
            "analysis_population": result["analysis_population"], "runs": len(result["runs"])}


def reproduce(manifest, output, *, bootstrap_samples=2000):
    manifest, output = Path(manifest).resolve(strict=True), Path(output).absolute()
    if output.exists():
        raise ReproductionError("Output already exists; reproduction never overwrites a previous run")
    exporter = load_module(Path(__file__).with_name("export_local_evidence.py"), "ru_local_exporter")
    # verify_bundle rejects invalid archives and unsafe paths before restoration.
    output.mkdir(parents=True)
    unpacked = output / "unpacked"
    verification = exporter.verify_bundle(manifest, unpacked)
    state = unpacked / "state"
    inventory, inventory_digest = verify_frozen_sources(state)
    analysis_path = state / "source/resumption/analysis.py"
    analysis = load_module(analysis_path, "ru_frozen_local_analysis")
    protocol = json_file(state / "protocol.json")
    measurement = protocol.get("measurement", {})
    budgets = tuple(measurement.get("observed_prefix_words", ()))
    if budgets != (128, 256, 512) or measurement.get("chunk_words") != 16:
        raise ReproductionError("Bundle protocol is outside the supported fixed-prefix design")
    bindings = {"protocol_sha256": sha((state / "protocol.json").read_bytes()),
                "corpus_sha256": sha((state / "corpus.json").read_bytes()),
                "source_inventory_sha256": inventory_digest,
                "verifier_source_sha256": inventory["files"].get("resumption/generator_audit.py")}
    ledger_digest = sha((state / "ledger.json").read_bytes())
    report = {"schema_version": 1, "purpose": "same_code_offline_reanalysis_not_new_replication",
              "network_or_model_calls": 0, "scientific_validity": "not_assessed", "E0": "not_passed",
              "manifest_sha256": sha(manifest.read_bytes()), "bundle_verification": verification,
              "bindings": bindings, "analysis_source_sha256": sha(analysis_path.read_bytes()),
              "analysis_version": getattr(analysis, "VERSION", None),
              "parameters": {"budgets": budgets, "bootstrap_samples": bootstrap_samples,
                             "order_controls": True}, "embedding_modes": {}, "analyses": []}
    results = state / "results.json"
    if not results.is_file():
        report["results_status"] = "unavailable_no_collection_results"
    else:
        originals = analysis.read_records(results)
        report["results_status"] = "retained_collection_records"
        report["results_sha256"] = sha(results.read_bytes())
        report["analyses"].append(run_analysis(analysis, originals, output / "analysis-lexical.json",
                                               budgets, bootstrap_samples))
        completion_path = unpacked / "bundle/derived-embedding-files.json"
        markers = json_file(completion_path).get("files", []) if completion_path.is_file() else []
        if len({marker.get("path") for marker in markers}) != len(markers):
            raise ReproductionError("Embedding completion inventory repeats an aggregate")
        completed = {}
        for model in MODELS:
            filename = "state/" + model.replace("/", "_") + "-embedded.json"
            marker = next((entry for entry in markers if entry.get("path") == filename), None)
            if marker is None or marker.get("file_present") is not True:
                report["embedding_modes"][model] = {
                    "status": "unavailable", "reason": "aggregate_absent_or_unfinished_at_export"}
                continue
            try:
                records, audit = reconstruct_embedding(state, marker, originals, bindings)
                report["analyses"].append(run_analysis(
                    analysis, records, output / ("analysis-" + model.replace("/", "_") + ".json"),
                    budgets, bootstrap_samples, model))
            except (ReproductionError, ValueError, TypeError, KeyError, OSError) as exc:
                report["embedding_modes"][model] = {
                    "status": "unavailable_invalid_whole_mode",
                    "reason": str(exc) if isinstance(exc, ReproductionError) else type(exc).__name__}
                continue
            report["embedding_modes"][model] = audit
            completed[model] = marker
            del records
            gc.collect()
        report["matched_embedding_status"] = "unavailable_both_complete_modes_required"
        if set(completed) == set(MODELS):
            # Common-prefix intersection occurs inside the frozen analysis before
            # every source/validation/test fit, separately for each word budget.
            first, _ = reconstruct_embedding(state, completed[MODELS[0]], originals, bindings)
            second, _ = reconstruct_embedding(state, completed[MODELS[1]], originals, bindings)
            for model, own, other, other_model in (
                    (MODELS[0], first, second, MODELS[1]), (MODELS[1], second, first, MODELS[0])):
                report["analyses"].append(run_analysis(
                    analysis, own, output / ("analysis-" + model.replace("/", "_") + "-matched.json"),
                    budgets, bootstrap_samples, model, other, other_model))
            del first, second
            gc.collect()
            report["matched_embedding_status"] = "supplementary_matched_analyses_completed"
    if sha((state / "ledger.json").read_bytes()) != ledger_digest:
        raise ReproductionError("Reanalysis unexpectedly changed the retained ledger")
    report["ledger_sha256_unchanged"] = ledger_digest
    report_path = output / "reproduction.json"
    report_path.write_bytes(encoded(report))
    return {"output": str(output.resolve()), "report": str(report_path.resolve()),
            "report_sha256": sha(report_path.read_bytes()), "analyses": len(report["analyses"]),
            "embedding_modes": {model: mode["status"] for model, mode in report["embedding_modes"].items()},
            "network_or_model_calls": 0, "scientific_validity": "not_assessed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="A new directory for verified restoration and analyses")
    parser.add_argument("--bootstrap-samples", type=int, default=2000,
                        help="Defaults to frozen analysis; reductions are explicit reproduction parameters")
    args = parser.parse_args()
    if args.bootstrap_samples < 0:
        parser.error("--bootstrap-samples must be nonnegative")
    try:
        summary = reproduce(args.manifest, args.output, bootstrap_samples=args.bootstrap_samples)
    except (ReproductionError, ValueError, KeyError, OSError) as exc:
        # Never echo untrusted raw text, parser documents or credentials.
        print("Offline reproduction failed: " +
              (str(exc) if isinstance(exc, ReproductionError) else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
