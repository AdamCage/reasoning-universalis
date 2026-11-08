"""Synthetic, offline checks of reconstruction from original embedding evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


reproduction = module(ROOT / "scripts/reproduce_local.py", "local_reproduction_tested")
exporter = module(ROOT / "scripts/export_local_evidence.py", "local_reproduction_exporter")


class LocalReproductionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.model = "baai/bge-m3"
        self.protocol = {"measurement": {"observed_prefix_words": [128, 256, 512], "chunk_words": 16}}
        self.write("protocol.json", self.protocol)
        self.write("corpus.json", {"synthetic_fixture": True})
        inventory = {"files": {}}
        for relative in ("resumption/analysis.py", "resumption/generator_audit.py"):
            data = (ROOT / relative).read_bytes()
            path = self.state / "source" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            inventory["files"][relative] = reproduction.sha(data)
        self.write("source-inventory.json", inventory)
        self.bindings = {
            "protocol_sha256": reproduction.sha((self.state / "protocol.json").read_bytes()),
            "corpus_sha256": reproduction.sha((self.state / "corpus.json").read_bytes()),
            "source_inventory_sha256": reproduction.sha((self.state / "source-inventory.json").read_bytes()),
            "verifier_source_sha256": inventory["files"]["resumption/generator_audit.py"]}
        self.originals = [{"trace_id": "synthetic-trace", "root_id": "synthetic-root", "model": "fixture",
                           "domain": "logic", "difficulty": "hard", "split": "test",
                           "text": " ".join("word" + str(index) for index in range(128)),
                           "correct": True, "status": "completed", "phase": "collection"}]
        self.write("results.json", {"phase": "collection", "records": self.originals})
        chunks = reproduction.expected_chunks(self.originals[0]["text"])
        identities = [["synthetic-trace", chunk["start"], chunk["end"]] for chunk in chunks]
        self.call_id = reproduction.sha(reproduction.encoded(
            {"kind": "embedding", "identity": identities,
             "protocol": self.bindings["protocol_sha256"], "model": self.model}))
        self.prefix = "calls/" + self.call_id + "/"
        self.request = {"model": self.model, "input": [chunk["text"] for chunk in chunks]}
        self.write(self.prefix + "request.json", self.request)
        self.response = {"http_status": 200, "json": {"model": self.model, "provider": "synthetic-provider",
                         "data": [{"index": index, "embedding": [float(index + 1)] + [0.0] * 1023}
                                  for index in range(len(chunks))]}}
        self.write(self.prefix + "response.json", self.response)
        self.reservation = {**self.bindings, "call_id": self.call_id, "kind": "embedding",
                            "identity": identities, "model": self.model,
                            "request_sha256": reproduction.sha(reproduction.encoded(self.request)),
                            "reservation_id": "synthetic-reservation"}
        self.write(self.prefix + "reservation.json", self.reservation)
        self.result = {**self.reservation, "http_status": 200,
                       "response_sha256": reproduction.sha(reproduction.encoded(self.response)),
                       "response": self.response}
        self.write(self.prefix + "result.json", self.result)
        self.write("ledger.json", [{"id": "synthetic-reservation", "state": "charged",
                                   "charged_or_reserved_rub": "1"}])
        self.route = {"model": self.model, "provider": "synthetic-provider", "dimension": 1024,
                      "first_response_sha256": self.result["response_sha256"],
                      "provider_identity_verified": True, "revision": "not_reported_not_inferred"}
        self.write("baai_bge-m3-embedding-route.json", self.route)
        records = copy.deepcopy(self.originals)
        records[0]["embeddings"] = {self.model: []}
        for chunk, item in zip(chunks, self.response["json"]["data"]):
            records[0]["embeddings"][self.model].append({
                **chunk, "vector": item["embedding"], "model_id": self.model,
                "identity_verified": True, "provider_identity_verified": True, "provider": "synthetic-provider",
                "input_sha256": reproduction.sha(chunk["text"].encode()),
                "request_sha256": self.reservation["request_sha256"],
                "response_sha256": self.result["response_sha256"]})
        self.aggregate = {"records": records, "embedding_model": self.model, "word_chunk_size": 16,
                          "max_observed_words": 512, "protocol_sha256": self.bindings["protocol_sha256"],
                          "embedding_route": self.route, "scientific_validity": "not_assessed"}
        self.write("baai_bge-m3-embedded.json", self.aggregate)
        markers = exporter.derived_embedding_registry(self.state, ())
        self.marker = next(row for row in markers["files"] if row["file_present"])

    def write(self, relative, value):
        path = self.state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(reproduction.encoded(value))

    def rebuild(self):
        return reproduction.reconstruct_embedding(self.state, self.marker, self.originals, self.bindings)

    def update_response(self):
        self.write(self.prefix + "response.json", self.response)
        self.result["response"] = self.response
        self.result["response_sha256"] = reproduction.sha(reproduction.encoded(self.response))
        self.write(self.prefix + "result.json", self.result)

    def test_exact_aggregate_reconstruction_and_frozen_source_inventory(self):
        records, audit = self.rebuild()
        self.assertEqual(records, self.aggregate["records"])
        self.assertEqual(audit["status"], "reconstructed_exact")
        self.assertEqual(audit["original_sha256"], reproduction.sha(reproduction.encoded(self.aggregate)))
        self.assertEqual(audit["validated_modes"][self.model]["chunks"], 8)
        reproduction.verify_frozen_sources(self.state)
        (self.state / "source/resumption/analysis.py").write_bytes(b"tampered")
        with self.assertRaisesRegex(reproduction.ReproductionError, "Frozen source differs"):
            reproduction.verify_frozen_sources(self.state)

    def test_original_request_sha_and_exact_chunk_text_are_required(self):
        self.request["input"][0] = "changed synthetic text"
        self.write(self.prefix + "request.json", self.request)
        with self.assertRaisesRegex(reproduction.ReproductionError, "request SHA-256"):
            self.rebuild()
        self.reservation["request_sha256"] = reproduction.sha(reproduction.encoded(self.request))
        self.write(self.prefix + "reservation.json", self.reservation)
        self.result["request_sha256"] = self.reservation["request_sha256"]
        self.write(self.prefix + "result.json", self.result)
        with self.assertRaisesRegex(reproduction.ReproductionError, "changed text"):
            self.rebuild()

    def test_invalid_batch_model_provider_dimension_and_vectors_fail_closed(self):
        for kind in ("model", "provider", "dimension", "bool_vector"):
            with self.subTest(kind=kind):
                saved = copy.deepcopy(self.response)
                if kind in ("model", "provider"):
                    self.response["json"][kind] = "different-synthetic-identity"
                elif kind == "dimension":
                    for item in self.response["json"]["data"]:
                        item["embedding"] = [1.0]
                else:
                    self.response["json"]["data"][0]["embedding"][0] = True
                self.update_response()
                with self.assertRaises(reproduction.ReproductionError):
                    self.rebuild()
                self.response = saved
                self.update_response()

    def test_missing_finalization_and_absent_completion_marker_are_not_recovered_as_success(self):
        (self.state / self.prefix / "result.json").unlink()
        with self.assertRaisesRegex(reproduction.ReproductionError, "no finalized"):
            self.rebuild()
        marker = copy.deepcopy(self.marker)
        marker["file_present"] = False
        with self.assertRaisesRegex(reproduction.ReproductionError, "absent or unfinished"):
            reproduction.reconstruct_embedding(self.state, marker, self.originals, self.bindings)

    def test_vector_slot_tampering_and_original_aggregate_digest_are_rejected(self):
        marker = copy.deepcopy(self.marker)
        marker["records"][0]["vector_slots"][0]["vector_sha256"] = "f" * 64
        with self.assertRaisesRegex(reproduction.ReproductionError, "vector/hash/metadata"):
            reproduction.reconstruct_embedding(self.state, marker, self.originals, self.bindings)
        marker = copy.deepcopy(self.marker)
        marker["original_sha256"] = "f" * 64
        with self.assertRaisesRegex(reproduction.ReproductionError, "original SHA-256/size"):
            reproduction.reconstruct_embedding(self.state, marker, self.originals, self.bindings)

    def test_response_original_bytes_are_bound_even_when_json_content_is_unchanged(self):
        response_path = self.state / self.prefix / "response.json"
        response_path.write_bytes(response_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(reproduction.ReproductionError, "response/result binding"):
            self.rebuild()

    def test_exported_bundle_reanalysis_is_offline_and_retains_ledger(self):
        exported = exporter.export_bundle(self.state, self.root / "bundle", project=self.root,
                                          include_project=False, secrets=())
        with patch.object(socket, "create_connection", side_effect=AssertionError("No network in reproduction")) as network:
            result = reproduction.reproduce(exported["manifest"], self.root / "reanalysis", bootstrap_samples=0)
            network.assert_not_called()
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(report["network_or_model_calls"], 0)
        self.assertEqual(report["embedding_modes"][self.model]["status"], "reconstructed_exact")
        self.assertEqual(report["embedding_modes"]["qwen/qwen3-embedding-8b"]["status"], "unavailable")
        self.assertEqual(len(report["analyses"]), 2)
        self.assertEqual(report["ledger_sha256_unchanged"], reproduction.sha((self.state / "ledger.json").read_bytes()))
        with self.assertRaisesRegex(reproduction.ReproductionError, "already exists"):
            reproduction.reproduce(exported["manifest"], self.root / "reanalysis")

    def test_valid_raw_batches_without_completed_aggregate_are_not_analyzed_semantically(self):
        (self.state / "baai_bge-m3-embedded.json").unlink()
        exported = exporter.export_bundle(self.state, self.root / "unfinished-bundle", project=self.root,
                                          include_project=False, secrets=())
        result = reproduction.reproduce(exported["manifest"], self.root / "unfinished-reanalysis", bootstrap_samples=0)
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(report["embedding_modes"][self.model]["status"], "unavailable")
        self.assertEqual(len(report["analyses"]), 1)
        self.assertEqual(report["matched_embedding_status"], "unavailable_both_complete_modes_required")

    def test_invalid_batch_excludes_the_whole_embedding_mode_but_retains_lexical_analysis(self):
        self.response["json"]["data"][0]["embedding"][0] = True
        self.update_response()
        exported = exporter.export_bundle(self.state, self.root / "invalid-bundle", project=self.root,
                                          include_project=False, secrets=())
        result = reproduction.reproduce(exported["manifest"], self.root / "invalid-reanalysis", bootstrap_samples=0)
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(report["embedding_modes"][self.model]["status"], "unavailable_invalid_whole_mode")
        self.assertEqual(len(report["analyses"]), 1)
        self.assertEqual(report["analyses"][0]["representation"], "lexical")

    def test_two_exact_completed_modes_enable_both_supplementary_matched_analyses(self):
        second_model = "qwen/qwen3-embedding-8b"
        request = copy.deepcopy(self.request)
        request["model"] = second_model
        identity = self.reservation["identity"]
        call_id = reproduction.sha(reproduction.encoded(
            {"kind": "embedding", "identity": identity,
             "protocol": self.bindings["protocol_sha256"], "model": second_model}))
        prefix = "calls/" + call_id + "/"
        reservation = {**self.bindings, "call_id": call_id, "kind": "embedding", "identity": identity,
                       "model": second_model, "request_sha256": reproduction.sha(reproduction.encoded(request)),
                       "reservation_id": "synthetic-second-reservation"}
        response = copy.deepcopy(self.response)
        response["json"]["model"] = second_model
        for item in response["json"]["data"]:
            item["embedding"] = item["embedding"][:8]
        response_sha = reproduction.sha(reproduction.encoded(response))
        result = {**reservation, "http_status": 200, "response_sha256": response_sha, "response": response}
        for name, value in (("request", request), ("response", response),
                            ("reservation", reservation), ("result", result)):
            self.write(prefix + name + ".json", value)
        route = {**self.route, "model": second_model, "dimension": 8, "first_response_sha256": response_sha}
        self.write("qwen_qwen3-embedding-8b-embedding-route.json", route)
        aggregate = copy.deepcopy(self.aggregate)
        aggregate.update(embedding_model=second_model, embedding_route=route)
        segments = aggregate["records"][0]["embeddings"].pop(self.model)
        aggregate["records"][0]["embeddings"][second_model] = segments
        for segment, item in zip(segments, response["json"]["data"]):
            segment.update(vector=item["embedding"], model_id=second_model,
                           request_sha256=reservation["request_sha256"], response_sha256=response_sha)
        self.write("qwen_qwen3-embedding-8b-embedded.json", aggregate)
        self.write("ledger.json", [{"id": name, "state": "charged", "charged_or_reserved_rub": "1"}
                                   for name in ("synthetic-reservation", "synthetic-second-reservation")])
        exported = exporter.export_bundle(self.state, self.root / "two-mode-bundle", project=self.root,
                                          include_project=False, secrets=())
        result = reproduction.reproduce(exported["manifest"], self.root / "two-mode-reanalysis", bootstrap_samples=0)
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(len(report["analyses"]), 5)
        self.assertEqual(report["matched_embedding_status"], "supplementary_matched_analyses_completed")
        self.assertEqual(sum(row["analysis_population"] == "supplementary_matched_embedding_prefixes"
                             for row in report["analyses"]), 2)


if __name__ == "__main__":
    unittest.main()
