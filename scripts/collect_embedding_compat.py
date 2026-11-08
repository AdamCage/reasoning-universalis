"""ASCII-case presentation repair for a frozen embedding collection.

Uses the original Runner.paid logical request, ledger, cache and source guards.
No alias, whitespace normalization, new state or automatic retry is introduced.
Requires a separately saved amendment bound to this exact script before use.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from resumption.runner import EMBEDDERS, Runner, Settings, chunks, read_json, sha
from stage0.config import parse_env
from stage0.runner import StopRun, encode
from stage0.traces import inspect_embeddings


RULE = "ascii_casefold_only"
DIRECTORY = "compatibility/embedding-ascii-casefold-v1"
AMENDMENT_PATH = "design/LOCAL_EMBEDDING_COMPAT_2026_11_08.json"
COLLECTOR_PATH = "scripts/collect_embedding_compat.py"


def require(condition, message):
    if not condition:
        raise StopRun(message)


def ascii_identity(returned, requested):
    return (isinstance(returned, str) and returned.isascii() and
            returned.casefold() == requested.casefold())


def immutable(path, data):
    if path.exists():
        require(path.read_bytes() == data, "Compatibility artifact changed after its binding")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def bind_compatibility(runner, amendment_path, protocol_path, results_path, *, project=PROJECT):
    """Persist a shared immutable engineering amendment, without rebinding core."""
    project = Path(project).resolve(strict=True)
    amendment_path = Path(amendment_path).resolve(strict=True)
    require(amendment_path == project / AMENDMENT_PATH, "Use the explicitly named compatibility amendment path")
    script_path = project / COLLECTOR_PATH
    script_bytes, amendment_bytes = script_path.read_bytes(), amendment_path.read_bytes()
    protocol_hash = sha(Path(protocol_path).read_bytes())
    amendment = json.loads(amendment_bytes)
    require(amendment.get("schema_version") == 1 and isinstance(amendment.get("amendment_id"), str)
            and bool(amendment["amendment_id"].strip()), "Invalid compatibility amendment identity")
    require(amendment.get("base_protocol_sha256") == protocol_hash == runner.protocol_digest,
            "Compatibility amendment refers to a different base protocol")
    require(amendment.get("script_sha256") == sha(script_bytes), "Compatibility collector script hash mismatch")
    require(amendment.get("model_identity_rule") == RULE, "Only ASCII case presentation compatibility is supported")
    models = amendment.get("models")
    require(isinstance(models, list) and models and len(models) == len(set(models))
            and all(model in EMBEDDERS for model in models), "Invalid compatibility amendment models")
    expected_routes = amendment.get("expected_routes")
    require(isinstance(expected_routes, dict) and set(expected_routes) == set(models),
            "Compatibility amendment needs one expected route per model")
    for model, route in expected_routes.items():
        require(isinstance(route, dict) and set(route) == {"provider", "dimension"}
                and isinstance(route["provider"], str) and bool(route["provider"].strip())
                and type(route["dimension"]) is int
                and (route["dimension"] == 1024 if model == "baai/bge-m3" else 1 <= route["dimension"] <= 4096),
                "Invalid expected embedding provider/dimension")
    try:
        created = datetime.fromisoformat(amendment["created_utc"].replace("Z", "+00:00"))
        require(created.tzinfo is not None, "Compatibility amendment timestamp needs a timezone")
    except (KeyError, TypeError, ValueError):
        raise StopRun("Invalid compatibility amendment timestamp") from None
    if runner.settings.key:
        require(runner.settings.key.encode() not in script_bytes + amendment_bytes,
                "Credential literal found in compatibility artifacts")
    binding = {"schema_version": 1, "amendment_id": amendment["amendment_id"],
               "amendment_sha256": sha(amendment_bytes), "collector_sha256": sha(script_bytes),
               "base_protocol_sha256": protocol_hash,
               "source_inventory_sha256": runner.source_inventory_digest,
               "corpus_sha256": runner.tasks_digest, "results_sha256": sha(Path(results_path).read_bytes()),
               "results_document_sha256": sha(encode(read_json(results_path))),
               "model_identity_rule": RULE, "models": models,
               "expected_routes": expected_routes,
               "amendment_path": AMENDMENT_PATH, "collector_path": COLLECTOR_PATH,
               "scientific_validity": "not_assessed"}
    with runner.locked():
        destination = runner.state / DIRECTORY
        immutable(destination / "amendment.json", amendment_bytes)
        immutable(destination / "collector.py", script_bytes)
        immutable(destination / "binding.json", encode(binding))
    return binding


def validate_batch(result, runner, model, body, route, expected):
    directory = runner.calls / result["call_id"]
    request_data, response_data = (directory / "request.json").read_bytes(), (directory / "response.json").read_bytes()
    require(sha(request_data) == result["request_sha256"] and json.loads(request_data) == body,
            "Compatibility request bytes or body mismatch")
    require(sha(response_data) == result["response_sha256"] and json.loads(response_data) == result["response"],
            "Compatibility response bytes or body mismatch")
    require(result["protocol_sha256"] == runner.protocol_digest and result["corpus_sha256"] == runner.tasks_digest,
            "Compatibility attempt refers to different bound inputs")
    payload = result["response"].get("json", {})
    inspection = inspect_embeddings(payload, model, len(body["input"]))
    returned = payload.get("model")
    require(result["http_status"] == 200 and result["response"].get("http_status") == 200
            and inspection["valid"] and ascii_identity(returned, model),
            "Embedding compatibility identity, HTTP status or shape validation failed; no retry")
    provider = payload.get("provider")
    require(isinstance(provider, str) and bool(provider.strip()), "Embedding compatibility requires an explicit provider")
    require(all(any(item["embedding"]) for item in payload["data"]), "Zero embedding vector is invalid")
    dimension = len(payload["data"][0]["embedding"])
    require(provider == expected["provider"] and dimension == expected["dimension"],
            "Embedding response differs from the amendment expected provider/dimension; no retry")
    observed = {"model": model, "provider": provider, "dimension": dimension}
    if route is not None:
        require(all(route.get(key) == value for key, value in observed.items()),
                "Embedding compatibility provider or dimension drift; raw attempt retained, no retry")
    return payload, observed


def collect_embeddings(runner, document, model, binding, batch_size=32):
    require(model in binding["models"] and model in EMBEDDERS and 1 <= batch_size <= 128,
            "Embedding model or batch size is outside the compatibility amendment")
    require(document.get("protocol_sha256") == runner.protocol_digest
            and document.get("corpus_sha256") == runner.tasks_digest,
            "Results differ from the original bound protocol/corpus")
    require(sha(encode(document)) == binding["results_document_sha256"],
            "Embedding compatibility input differs from the exact bound results")
    records = document["records"]
    targets = []
    for record in records:
        if record.get("status") != "completed":
            continue
        segments = chunks(record["text"])
        record.setdefault("embeddings", {})[model] = segments
        targets.extend((record["trace_id"], segment) for segment in segments)
    route_path = runner.state / (model.replace("/", "_") + "-embedding-route.json")
    route = read_json(route_path) if route_path.exists() else None
    expected = binding["expected_routes"][model]
    cached_batches = 0
    for offset in range(0, len(targets), batch_size):
        batch = targets[offset:offset + batch_size]
        # Deliberately identical to frozen Runner.embed: this reuses the exact
        # known first attempt and cannot repackage an unknown attempt as new.
        body = {"model": model, "input": [segment["text"] for _, segment in batch]}
        identity = [(trace, segment["start"], segment["end"]) for trace, segment in batch]
        current_route = read_json(route_path) if route_path.exists() else None
        if current_route is not None:
            require(current_route.get("model") == model and all(current_route.get(key) == value
                    for key, value in expected.items()),
                    "Stored embedding route differs from the immutable amendment before dispatch")
            if route is not None:
                require(current_route == route, "Stored embedding route changed before dispatch")
            route = current_route
        result = runner.paid("embedding", identity, model, body)
        payload, observed = validate_batch(result, runner, model, body, route, expected)
        reused = bool(result.get("reused_record_without_resend"))
        cached_batches += reused
        if route is None:
            route = {**observed, "first_response_sha256": result["response_sha256"],
                     "provider_identity_verified": True, "revision": "not_reported_not_inferred",
                     "identity_rule": RULE, "amendment_sha256": binding["amendment_sha256"],
                     "collector_sha256": binding["collector_sha256"]}
            runner.save(route_path, route)
        receipt = {"schema_version": 1, "call_id": result["call_id"], "requested_model": model,
                   "returned_model_id": payload["model"], "provider": observed["provider"],
                   "dimension": observed["dimension"], "identity_rule": RULE,
                   "request_sha256": result["request_sha256"], "response_sha256": result["response_sha256"],
                   "amendment_sha256": binding["amendment_sha256"], "collector_sha256": binding["collector_sha256"],
                   "cached_without_resend": reused, "scientific_validity": "not_assessed"}
        with runner.locked():
            receipt_path = runner.calls / result["call_id"] / "embedding-compatibility.json"
            if receipt_path.exists():
                previous = read_json(receipt_path)
                # Whether a later replay hit cache is execution bookkeeping;
                # the initial acceptance receipt remains unchanged.
                require({k: v for k, v in previous.items() if k != "cached_without_resend"} ==
                        {k: v for k, v in receipt.items() if k != "cached_without_resend"},
                        "Compatibility receipt differs from the existing acceptance")
            else:
                runner.save(receipt_path, receipt)
        for item in sorted(payload["data"], key=lambda row: row["index"]):
            _, segment = batch[item["index"]]
            segment.update(vector=item["embedding"], model_id=model, returned_model_id=payload["model"],
                           identity_verified=True, identity_rule=RULE,
                           input_sha256=sha(segment["text"].encode("utf-8")),
                           request_sha256=result["request_sha256"], response_sha256=result["response_sha256"],
                           provider=observed["provider"], provider_identity_verified=True)
    execution = {key: binding[key] for key in ("amendment_path", "amendment_sha256", "collector_path",
                                              "collector_sha256", "model_identity_rule", "base_protocol_sha256")}
    execution.update(canonical_requested_model=model, returned_model_identity_preserved=True,
                     state_binding_path=DIRECTORY + "/binding.json")
    output = {"records": records, "embedding_model": model, "word_chunk_size": 16,
              "max_observed_words": 512, "budget": runner.budget(), "protocol_sha256": runner.protocol_digest,
              "embedding_route": route, "scientific_validity": "not_assessed", "identity_rule": RULE,
              "execution_compatibility": execution, "cached_batches_reused": cached_batches}
    runner.save(runner.state / (model.replace("/", "_") + "-embedded.json"), output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--amendment", type=Path, required=True)
    parser.add_argument("--embedding-model", choices=EMBEDDERS, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--cap-total-rub", type=Decimal, default=Decimal("3000"))
    parser.add_argument("--collection-cap-rub", type=Decimal, default=Decimal("2900"))
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    try:
        require(args.state.is_dir() and (args.state / "ledger.json").is_file(),
                "Use the existing live state and ledger; compatibility cannot initialize a new budget")
        settings_env = {**(parse_env(args.env_file) if args.env_file else {}), **os.environ}
        require(settings_env.get("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1") == "https://routerai.ru/api/v1",
                "Only the prescribed RouterAI URL is supported")
        protocol = read_json(args.protocol)
        generation = protocol["generation"]
        settings = Settings(state=args.state, key=settings_env.get("ROUTERAI_API_KEY", ""),
                            cap=args.cap_total_rub, collection_cap=args.collection_cap_rub,
                            max_tokens=generation["max_output_tokens"], temperature=generation["temperature"],
                            top_p=generation["top_p"], seed=generation["seed"],
                            timeout=generation.get("request_timeout_seconds", 900),
                            deadline=generation["dispatch_deadline_utc"])
        runner = Runner(settings)
        runner.bind(args.protocol)
        binding = bind_compatibility(runner, args.amendment, args.protocol, args.results)
        result = collect_embeddings(runner, read_json(args.results), args.embedding_model, binding, args.batch_size)
        print(json.dumps({"completed": True, "model": args.embedding_model, "records": len(result["records"]),
                          "cached_batches_reused": result["cached_batches_reused"], "budget": result["budget"],
                          "identity_rule": RULE, "scientific_validity": "not_assessed"}))
    except StopRun as exc:
        print(json.dumps({"stopped": True, "reason": str(exc)}))
        raise SystemExit(2) from None
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"stopped": True, "error_type": type(exc).__name__}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
