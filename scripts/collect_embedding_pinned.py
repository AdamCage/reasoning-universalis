"""A separately amended provider-pinned embedding measurement condition.

Known valid preflight observations can be reused. A known rejected route can be
measured under this declared new condition only when explicitly listed. Any
unknown attempt on the same original chunk blocks the condition, across all
namespaces. The frozen Runner still owns paid dispatch, cache and the ledger.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from resumption.runner import EMBEDDERS, Runner, Settings, chunks, read_json, sha
from stage0.config import parse_env
from stage0.runner import StopRun, encode
from stage0.traces import inspect_embeddings


RULE = "ascii_casefold_only"
AMENDMENT_PATH = "design/LOCAL_EMBEDDING_PINNED_2026_11_08.json"
COLLECTOR_PATH = "scripts/collect_embedding_pinned.py"
HEX = re.compile(r"^[0-9a-f]{64}$")


def require(condition, message):
    if not condition:
        raise StopRun(message)


def immutable(path, data):
    if path.exists():
        require(path.read_bytes() == data, "Provider condition artifact changed after binding")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def ascii_identity(returned, requested):
    return isinstance(returned, str) and returned.isascii() and returned.casefold() == requested.casefold()


def bind_condition(runner, amendment_path, protocol_path, results_path, *, project=PROJECT):
    project = Path(project).resolve(strict=True)
    amendment_path = Path(amendment_path).resolve(strict=True)
    require(amendment_path == project / AMENDMENT_PATH, "Use the explicitly named provider condition amendment")
    amendment_bytes = amendment_path.read_bytes()
    script_bytes = (project / COLLECTOR_PATH).read_bytes()
    amendment = json.loads(amendment_bytes)
    protocol_hash = sha(Path(protocol_path).read_bytes())
    require(amendment.get("schema_version") == 1 and isinstance(amendment.get("amendment_id"), str)
            and bool(amendment["amendment_id"].strip()), "Invalid provider condition amendment identity")
    require(amendment.get("base_protocol_sha256") == protocol_hash == runner.protocol_digest,
            "Provider condition refers to a different base protocol")
    require(amendment.get("script_sha256") == sha(script_bytes), "Provider condition collector hash mismatch")
    require(amendment.get("model_identity_rule") == RULE, "Only ASCII case presentation compatibility is supported")
    models = amendment.get("models")
    require(isinstance(models, list) and models and len(models) == len(set(models))
            and all(model in EMBEDDERS for model in models), "Invalid provider condition models")
    routes = amendment.get("expected_routes")
    require(isinstance(routes, dict) and set(routes) == set(models), "Expected provider routes are incomplete")
    for model, route in routes.items():
        require(isinstance(route, dict) and set(route) == {"provider", "dimension"}
                and isinstance(route["provider"], str) and bool(route["provider"].strip())
                and type(route["dimension"]) is int
                and (route["dimension"] == 1024 if model == EMBEDDERS[0] else 1 <= route["dimension"] <= 4096),
                "Invalid expected provider/dimension")
    try:
        created = datetime.fromisoformat(amendment["created_utc"].replace("Z", "+00:00"))
        require(created.tzinfo is not None, "Provider amendment timestamp needs a timezone")
    except (KeyError, TypeError, ValueError):
        raise StopRun("Invalid provider amendment timestamp") from None
    parents, replacements = amendment.get("parent_call_ids"), amendment.get("allowed_replacement_call_ids")
    require(isinstance(parents, list) and len(parents) == len(set(parents)) and all(HEX.fullmatch(p) for p in parents),
            "Invalid declared parent attempt roster")
    require(isinstance(replacements, list) and len(replacements) == len(set(replacements))
            and set(replacements) <= set(parents), "Replacement attempts must be explicitly declared parents")
    if runner.settings.key:
        require(runner.settings.key.encode() not in script_bytes + amendment_bytes,
                "Credential literal found in provider condition artifacts")
    document = read_json(results_path)
    require(document.get("protocol_sha256") == runner.protocol_digest
            and document.get("corpus_sha256") == runner.tasks_digest, "Provider condition input binding mismatch")
    completed = [row["trace_id"] for row in document["records"] if row.get("status") == "completed"]
    require(len(completed) == len(set(completed)), "Provider condition repeats an original trace ID")
    condition = sha(amendment_bytes)
    binding = {"schema_version": 1, "condition_sha256": condition, "amendment_id": amendment["amendment_id"],
               "amendment_sha256": condition, "collector_sha256": sha(script_bytes),
               "base_protocol_sha256": protocol_hash, "source_inventory_sha256": runner.source_inventory_digest,
               "corpus_sha256": runner.tasks_digest, "results_sha256": sha(Path(results_path).read_bytes()),
               "results_document_sha256": sha(encode(document)), "model_identity_rule": RULE,
               "models": models, "expected_routes": routes, "parent_call_ids": parents,
               "allowed_replacement_call_ids": replacements, "amendment_path": AMENDMENT_PATH,
               "collector_path": COLLECTOR_PATH, "scientific_validity": "not_assessed"}
    mapping = {"schema_version": 1, "condition_sha256": condition,
               "trace_mapping": {condition + ":" + original: original for original in completed}}
    with runner.locked():
        ledger = {row["id"]: row for row in runner._check_ledger().rows}
        for call_id in parents:
            parent = runner.calls / call_id
            require(all((parent / name).is_file() for name in
                        ("request.json", "reservation.json", "response.json", "result.json")),
                    "Declared parent embedding attempt is missing; no new budget/state is permitted")
            reservation, result = read_json(parent / "reservation.json"), read_json(parent / "result.json")
            reservation_id = reservation.get("reservation_id")
            require(reservation.get("kind") == "embedding" and reservation_id in ledger
                    and result.get("reservation_id") == reservation_id
                    and result.get("http_status") is not None,
                    "Declared parent attempt is unresolved or absent from the shared ledger")
            require(Decimal(ledger[reservation_id]["charged_or_reserved_rub"]) >= Decimal(reservation["reservation_rub"]),
                    "Declared parent commitment was reduced in the shared ledger")
        directory = runner.state / "embedding-conditions" / condition
        immutable(directory / "amendment.json", amendment_bytes)
        immutable(directory / "collector.py", script_bytes)
        immutable(directory / "binding.json", encode(binding))
        immutable(directory / "mapping.json", encode(mapping))
    return binding, mapping


def valid_payload(payload, model, count, expected):
    inspected = inspect_embeddings(payload, model, count)
    return (inspected["valid"] and ascii_identity(payload.get("model"), model)
            and payload.get("provider") == expected["provider"]
            and len(payload["data"][0]["embedding"]) == expected["dimension"]
            and all(any(row["embedding"]) for row in payload["data"]))


class AttemptIndex:
    """Incremental journal index, resolving condition IDs to original chunks."""
    def __init__(self, runner, model, targets, binding):
        self.runner, self.model, self.binding = runner, model, binding
        self.target_keys = set(targets)
        self.target_texts = {segment["text"] for segment in targets.values()}
        self.expected = binding["expected_routes"][model]
        self.cache = {}
        self.intent_cache = {}

    def mappings(self):
        mappings = {}
        for path in sorted((self.runner.state / "embedding-conditions").glob("*/mapping.json")):
            value = read_json(path)
            condition = path.parent.name
            require(HEX.fullmatch(condition) and value.get("condition_sha256") == condition,
                    "Invalid condition-to-original mapping")
            for paid, original in value["trace_mapping"].items():
                require(paid == condition + ":" + original and paid not in mappings,
                        "Conflicting condition-to-original mapping")
                mappings[paid] = original
        return mappings

    def read(self, directory, mappings):
        request_path = directory / "request.json"
        if not request_path.exists():
            return None
        body = read_json(request_path)
        if body.get("model") != self.model or "input" not in body:
            return None
        reservation_path = directory / "reservation.json"
        if not reservation_path.exists():
            require(not self.target_texts.intersection(body.get("input", [])),
                    "Unresolved embedding request lacks reservation identity; no new condition allowed")
            return None
        context = read_json(reservation_path)
        if context.get("kind") != "embedding":
            return None
        identities = context.get("identity")
        logical_id = sha(encode({"kind": "embedding", "identity": identities,
                                 "protocol": context.get("protocol_sha256"), "model": context.get("model")}))
        require(context.get("call_id") == directory.name == logical_id
                and context.get("model") == self.model
                and sha(request_path.read_bytes()) == context.get("request_sha256"),
                "Embedding reservation identity/request integrity mismatch")
        require(isinstance(identities, list) and len(identities) == len(body["input"]),
                "Embedding attempt identity/input roster mismatch")
        original = []
        for item in identities:
            require(isinstance(item, list) and len(item) == 3, "Invalid underlying embedding chunk identity")
            paid_trace, start, end = item
            if ":" in paid_trace:
                require(paid_trace in mappings, "Embedding condition mapping is missing; cannot resolve underlying chunks")
                trace = mappings[paid_trace]
            else:
                trace = paid_trace
            original.append((trace, start, end))
        touched = self.target_keys.intersection(original)
        if not touched:
            return None
        ledger = {row["id"]: row for row in self.runner._check_ledger().rows}
        reservation_id = context.get("reservation_id")
        require(reservation_id in ledger and
                Decimal(ledger[reservation_id]["charged_or_reserved_rub"]) >= Decimal(context["reservation_rub"]),
                "Embedding attempt commitment is absent or reduced in the shared ledger")
        result_path, response_path = directory / "result.json", directory / "response.json"
        require(result_path.exists() and response_path.exists(),
                "Unresolved embedding attempt on an original chunk blocks the provider condition")
        result = read_json(result_path)
        require(all(key in result and result[key] == value for key, value in context.items()),
                "Embedding result differs from its original reservation context")
        require(result.get("reservation_id") == reservation_id, "Embedding result/ledger reservation mismatch")
        response_data, request_data = response_path.read_bytes(), request_path.read_bytes()
        response = json.loads(response_data)
        require(result.get("http_status") is not None and response.get("http_status") is not None
                and not response.get("network_error"),
                "Unknown/network embedding attempt on an original chunk blocks the provider condition")
        require(result.get("call_id") == directory.name and sha(request_data) == result.get("request_sha256")
                and sha(response_data) == result.get("response_sha256") and result.get("response") == response,
                "Embedding journal provenance mismatch")
        require(result.get("protocol_sha256") == self.runner.protocol_digest
                and result.get("corpus_sha256") == self.runner.tasks_digest
                and result.get("source_inventory_sha256") == self.runner.source_inventory_digest,
                "Embedding attempt differs from the original bound research inputs")
        payload = response.get("json", {})
        valid = result["http_status"] == 200 and response["http_status"] == 200 and valid_payload(
            payload, self.model, len(body["input"]), self.expected)
        current = all(paid[0].startswith(self.binding["condition_sha256"] + ":") for paid in identities)
        pinned = body.get("provider") == {"order": [self.expected["provider"]], "allow_fallbacks": False}
        if current:
            require(pinned, "Current provider condition request was not pinned")
        else:
            require(directory.name in self.binding["parent_call_ids"],
                    "Prior embedding attempt was not declared in the new condition")
        if not valid:
            require(not current and directory.name in self.binding["allowed_replacement_call_ids"],
                    "Known rejected attempt cannot be retried without a separately declared condition")
        vectors = {row["index"]: row["embedding"] for row in payload.get("data", [])} if valid else {}
        # Retain only vectors and provenance: raw-body/base64 duplicates stay on disk.
        return {"call_id": directory.name, "valid": valid, "current": current, "pinned": pinned,
                "identities": identities, "original": original, "inputs": body["input"], "vectors": vectors,
                "returned_model_id": payload.get("model"), "provider": payload.get("provider"),
                "request_sha256": result["request_sha256"], "response_sha256": result["response_sha256"]}

    def refresh(self):
        mappings = self.mappings()
        for path in sorted((self.runner.state / "embedding-conditions").glob("*/intents/*.json")):
            intent = read_json(path)
            if intent.get("model") != self.model:
                continue
            original = {tuple(row) for row in intent["original_identity"]}
            if not original.intersection(self.target_keys):
                continue
            result_path = self.runner.calls / path.stem / "result.json"
            require(result_path.exists(),
                    "Unresolved provider-condition intent on an original chunk blocks new dispatch")
            stat = result_path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            cached = self.intent_cache.get(result_path)
            if cached is None or cached[0] != signature:
                result = read_json(result_path)
                cached = (signature, result.get("http_status"), result.get("response", {}).get("network_error"))
                self.intent_cache[result_path] = cached
            require(cached[1] is not None and not cached[2],
                    "Unknown provider-condition attempt blocks new dispatch across namespaces")
        entries = []
        for directory in sorted(self.runner.calls.iterdir()):
            if not directory.is_dir():
                continue
            signature = tuple((name, (directory / name).stat().st_size, (directory / name).stat().st_mtime_ns)
                              for name in ("request.json", "reservation.json", "result.json", "response.json")
                              if (directory / name).exists())
            previous = self.cache.get(directory.name)
            if previous is None or previous[0] != signature:
                previous = (signature, self.read(directory, mappings))
                self.cache[directory.name] = previous
            if previous[1] is not None:
                entries.append(previous[1])
        return entries


def save_aggregate(runner, path, value):
    """Runner-compatible JSON streamed to disk, avoiding a second giant string."""
    temporary = path.with_name(path.name + ".provider-condition.tmp")
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    secret, tail = runner.settings.key, ""
    with temporary.open("w", encoding="utf-8", newline="") as output:
        for block in encoder.iterencode(value):
            if secret:
                combined = tail + block
                require(secret not in combined, "Credential detected in provider aggregate")
                tail = combined[-len(secret):]
            output.write(block)
    os.replace(temporary, path)


def collect_embeddings(runner, document, model, binding, mapping, batch_size=32):
    require(model in binding["models"] and model in EMBEDDERS and 1 <= batch_size <= 128,
            "Model or batch size is outside the provider condition")
    require(sha(encode(document)) == binding["results_document_sha256"],
            "Provider condition input differs from the exact bound results")
    condition = binding["condition_sha256"]
    expected = binding["expected_routes"][model]
    directory = runner.state / "embedding-conditions" / condition
    require(read_json(directory / "binding.json") == binding and read_json(directory / "mapping.json") == mapping,
            "Provider condition binding/mapping changed")
    targets, ordered = {}, []
    for record in document["records"]:
        if record.get("status") != "completed":
            continue
        require(mapping["trace_mapping"].get(condition + ":" + record["trace_id"]) == record["trace_id"],
                "Original trace is missing from the condition mapping")
        segments = chunks(record["text"])
        record.setdefault("embeddings", {})[model] = segments
        for segment in segments:
            key = (record["trace_id"], segment["start"], segment["end"])
            require(key not in targets, "Provider condition repeats a chunk")
            targets[key] = segment
            ordered.append(key)
    index = AttemptIndex(runner, model, targets, binding)
    accepted, rejections, receipts = {}, {}, {}

    def accept(entries):
        # Current-condition records precede reused declared parents; within each
        # class the call ID fixes selection, independent of scientific outcomes.
        for entry in sorted(entries, key=lambda row: (not row["current"], row["call_id"])):
            for position, key in enumerate(entry["original"]):
                if key not in targets:
                    continue
                require(targets[key]["text"] == entry["inputs"][position], "Embedding request text changed for an original chunk")
                if not entry["valid"]:
                    rejections.setdefault(key, set()).add(entry["call_id"])
                elif key not in accepted:
                    accepted[key] = (entry, position)

    # This scans every old/new attempt before any new measurement, including
    # unresolved attempts hidden behind a different declared condition namespace.
    with runner.locked():
        accept(index.refresh())
    missing = [key for key in ordered if key not in accepted]
    for offset in range(0, len(missing), batch_size):
        original_keys = missing[offset:offset + batch_size]
        identity = [(condition + ":" + trace, start, end) for trace, start, end in original_keys]
        body = {"model": model, "input": [targets[key]["text"] for key in original_keys],
                "provider": {"order": [expected["provider"]], "allow_fallbacks": False}}
        with runner.locked():
            require(read_json(directory / "binding.json") == binding and read_json(directory / "mapping.json") == mapping,
                    "Provider condition binding/mapping changed before dispatch")
            accept(index.refresh())
            require(not any(key in accepted for key in original_keys),
                    "Another worker completed this provider batch; resume offline instead of creating a new request")
            # Explicit prospective intent resolves every namespace before paid().
            intent = {"schema_version": 1, "condition_sha256": condition, "model": model,
                      "original_identity": [list(key) for key in original_keys], "paid_identity": identity,
                      "request_body_sha256": sha(encode(body)), "amendment_sha256": condition}
            intent_id = sha(encode({"kind": "embedding", "identity": identity,
                                   "protocol": runner.protocol_digest, "model": model}))
            immutable(directory / "intents" / (intent_id + ".json"), encode(intent))
        runner.paid("embedding", identity, model, body)
        with runner.locked():
            accept(index.refresh())
        require(all(key in accepted for key in original_keys),
                "Pinned provider response was rejected; the known attempt will not be repeated")
    require(len(accepted) == len(targets), "Provider condition did not cover the complete declared target set")
    route_path = directory / (model.replace("/", "_") + "-embedding-route.json")
    first = accepted[ordered[0]][0] if ordered else None
    route = ({"model": model, **expected, "first_response_sha256": first["response_sha256"],
              "provider_identity_verified": True, "revision": "not_reported_not_inferred", "identity_rule": RULE,
              "condition_sha256": condition, "amendment_sha256": condition,
              "collector_sha256": binding["collector_sha256"]} if first else None)
    for key in ordered:
        entry, position = accepted[key]
        receipt_path = "calls/" + entry["call_id"] + "/embedding-pinned-" + condition + ".json"
        parents = sorted(rejections.get(key, set()))
        segment = targets[key]
        segment.update(vector=entry["vectors"][position], model_id=model, returned_model_id=entry["returned_model_id"],
                       identity_verified=True, identity_rule=RULE, input_sha256=sha(segment["text"].encode("utf-8")),
                       request_sha256=entry["request_sha256"], response_sha256=entry["response_sha256"],
                       provider=expected["provider"], provider_identity_verified=True,
                       measurement_condition_sha256=condition, embedding_call_id=entry["call_id"],
                       paid_trace_id=entry["identities"][position][0], pinned_receipt_path=receipt_path,
                       reused_known_valid=not entry["current"], request_route_pinned=entry["pinned"],
                       parent_rejected_call_ids=parents)
        if entry["call_id"] not in receipts:
            receipts[entry["call_id"]] = {"schema_version": 1, "condition_sha256": condition,
                "call_id": entry["call_id"], "request_sha256": entry["request_sha256"],
                "response_sha256": entry["response_sha256"], "requested_model": model,
                "returned_model_id": entry["returned_model_id"], **expected, "identity_rule": RULE,
                "amendment_sha256": condition, "collector_sha256": binding["collector_sha256"],
                "accepted_source": "condition_request" if entry["current"] else "reused_known_valid_unpinned",
                "body_provider_pinned": entry["pinned"], "input_mapping": [], "parent_rejected_call_ids": [],
                "scientific_validity": "not_assessed"}
        receipt = receipts[entry["call_id"]]
        receipt["input_mapping"].append({"response_index": position, "original_trace_id": key[0],
            "paid_trace_id": entry["identities"][position][0], "start": key[1], "end": key[2],
            "input_sha256": segment["input_sha256"]})
        receipt["parent_rejected_call_ids"] = sorted(set(receipt["parent_rejected_call_ids"]) | set(parents))
    with runner.locked():
        if route is not None:
            immutable(route_path, encode(route))
        for call_id, receipt in receipts.items():
            immutable(runner.calls / call_id / ("embedding-pinned-" + condition + ".json"), encode(receipt))
    execution = {key: binding[key] for key in ("amendment_path", "amendment_sha256", "collector_path", "collector_sha256",
                                              "model_identity_rule", "base_protocol_sha256", "condition_sha256",
                                              "parent_call_ids", "allowed_replacement_call_ids")}
    execution.update(canonical_requested_model=model, returned_model_identity_preserved=True, **expected,
                     state_binding_path="embedding-conditions/" + condition + "/binding.json",
                     condition_mapping_path="embedding-conditions/" + condition + "/mapping.json")
    output = {"records": document["records"], "embedding_model": model, "word_chunk_size": 16,
              "max_observed_words": 512, "budget": runner.budget(), "protocol_sha256": runner.protocol_digest,
              "embedding_route": route, "scientific_validity": "not_assessed", "identity_rule": RULE,
              "measurement_condition_sha256": condition, "execution_pinned_condition": execution,
              "reused_known_chunks": sum(not accepted[key][0]["current"] for key in ordered),
              "new_condition_chunks": sum(accepted[key][0]["current"] for key in ordered)}
    save_aggregate(runner, runner.state / (model.replace("/", "_") + "-embedded.json"), output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "results", "protocol", "amendment"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--embedding-model", choices=EMBEDDERS, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--cap-total-rub", type=Decimal, default=Decimal("3000"))
    parser.add_argument("--collection-cap-rub", type=Decimal, default=Decimal("2900"))
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    try:
        require(args.state.is_dir() and (args.state / "ledger.json").is_file(),
                "Use the existing live state and ledger; no new budget is initialized")
        values = {**(parse_env(args.env_file) if args.env_file else {}), **os.environ}
        require(values.get("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1") == "https://routerai.ru/api/v1",
                "Only the prescribed RouterAI URL is supported")
        generation = read_json(args.protocol)["generation"]
        runner = Runner(Settings(state=args.state, key=values.get("ROUTERAI_API_KEY", ""),
            cap=args.cap_total_rub, collection_cap=args.collection_cap_rub,
            max_tokens=generation["max_output_tokens"], temperature=generation["temperature"],
            top_p=generation["top_p"], seed=generation["seed"], timeout=generation.get("request_timeout_seconds", 900),
            deadline=generation["dispatch_deadline_utc"]))
        runner.bind(args.protocol)
        binding, mapping = bind_condition(runner, args.amendment, args.protocol, args.results)
        output = collect_embeddings(runner, read_json(args.results), args.embedding_model, binding, mapping, args.batch_size)
        print(json.dumps({key: output[key] for key in ("embedding_model", "reused_known_chunks", "new_condition_chunks",
                                                       "measurement_condition_sha256", "budget", "scientific_validity")}))
    except StopRun as exc:
        print(json.dumps({"stopped": True, "reason": str(exc)}))
        raise SystemExit(2) from None
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"stopped": True, "error_type": type(exc).__name__}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
