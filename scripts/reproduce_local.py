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


def embedding_calls(state, model, records, bindings):
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
    vectors, batch_count, response_hashes = {}, 0, set()
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
                or payload.get("model") != model):
            raise ReproductionError("Embedding batch has invalid HTTP/API/model status")
        provider = payload.get("provider")
        provider = provider if isinstance(provider, str) and provider.strip() else None
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
        if any(route.get(key) != value for key, value in
               (("model", model), ("provider", provider), ("dimension", dimension))):
            raise ReproductionError("Embedding provider/dimension route drift")
        response_hash = sha(raw["response"])
        response_hashes.add(response_hash)
        for item in items:
            index = item["index"]
            key = tuple(identity[index])
            if key in vectors or key not in chunks or inputs[index] != chunks[key]["text"]:
                raise ReproductionError("Embedding chunk is repeated, absent, or has changed text")
            vectors[key] = {"vector": item["embedding"], "provider": provider,
                            "request_sha256": sha(raw["request"]), "response_sha256": response_hash,
                            "input_sha256": sha(inputs[index].encode("utf-8"))}
        batch_count += 1
    if not vectors or route.get("first_response_sha256") not in response_hashes:
        raise ReproductionError("Completed embedding route has no matching original responses")
    return vectors, {"batches": batch_count, "chunks": len(vectors), "route": route}


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
        maps[needed_model], audits[needed_model] = embedding_calls(state, needed_model, originals, bindings)
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
                    or any(segment.get(key) != value for key, value in found.items() if key != "vector")
                    or segment.get("text") != lookup[trace_id]["text"][segment["start"]:segment["end"]]):
                raise ReproductionError("Recorded embedding vector/hash/metadata differs from raw evidence")
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
    return restored, {"status": "reconstructed_exact", "model": model,
                      "original_sha256": digest, "original_bytes": count,
                      "records": len(restored), "validated_modes": audits}


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
