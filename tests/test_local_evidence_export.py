"""Synthetic export roundtrips and fail-closed archive/secret guards."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_evidence_export", ROOT / "scripts/export_local_evidence.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class LocalEvidenceExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.call_id = "a" * 64
        self.call = self.state / "calls" / self.call_id
        self.call.mkdir(parents=True)
        self.write("ledger.json", [{"id": "historical", "state": "pending", "charged_or_reserved_rub": "2"},
                                   {"id": "reservation-1", "state": "unknown", "charged_or_reserved_rub": "1"}])
        self.write("protocol.json", {"synthetic_fixture": True})
        self.write("corpus.json", {"tasks": [], "synthetic_fixture": True})
        self.write("source-inventory.json", {"files": {}})
        self.write("calls/" + self.call_id + "/request.json", {"model": "fixture"})
        self.write("calls/" + self.call_id + "/reservation.json",
                   {"call_id": self.call_id, "reservation_id": "reservation-1", "kind": "generation", "model": "fixture"})
        self.response = {"http_status": None, "json": {"fixture": base64.b64encode(os.urandom(2048)).decode()}}
        self.write("calls/" + self.call_id + "/response.json", self.response)
        self.write("calls/" + self.call_id + "/result.json", {"call_id": self.call_id, "response": self.response})

    def write(self, relative, value):
        target = self.state / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(exporter.encoded(value))

    def export(self, name="bundle", secrets=()):
        return exporter.export_bundle(self.state, self.root / name, project=self.root,
                                      include_project=False, secrets=secrets,
                                      chunk_bytes=256, shard_bytes=1024)

    def test_shards_roundtrip_unknown_ledger_and_exact_result_restoration(self):
        (self.state / ".env").write_text("PRIVATE=not-an-export\n")
        result = self.export()
        self.assertTrue(result["verified"])
        manifest = json.loads(Path(result["manifest"]).read_bytes())
        self.assertGreater(len(manifest["shards"]), 1)
        self.assertTrue(all(row["uncompressed_bytes"] <= 1024 for row in manifest["shards"]))
        row = next(r for r in manifest["files"] if r["path"].endswith("/result.json"))
        self.assertEqual(row["transformation"]["kind"], "omit_duplicate_result_response")
        self.assertLess(row["stored_bytes"], row["original_bytes"])
        destination = self.root / "restored"
        exporter.verify_bundle(result["manifest"], destination)
        self.assertFalse((destination / "state/.env").exists())
        for source in self.state.rglob("*.json"):
            restored = destination / "state" / source.relative_to(self.state)
            self.assertEqual(restored.read_bytes(), source.read_bytes())
        registry = json.loads((destination / "bundle/attempt-registry.json").read_bytes())
        self.assertEqual(registry["counts"], {"unknown": 1})
        self.assertTrue(registry["attempts"][0]["response_retained"])
        self.assertEqual(registry["ledger_rows_without_matching_attempt_directory"], 1)

    def test_tampered_shard_and_unsafe_restored_path_are_rejected(self):
        result = self.export()
        manifest_path = Path(result["manifest"])
        manifest = json.loads(manifest_path.read_bytes())
        manifest["files"][0]["path"] = "state/../../escape.json"
        manifest_path.write_bytes(exporter.encoded(manifest))
        with self.assertRaisesRegex(exporter.ExportError, "Unsafe bundle path"):
            exporter.verify_bundle(manifest_path)
        result = self.export("another-bundle")
        manifest = json.loads(Path(result["manifest"]).read_bytes())
        shard = Path(result["manifest"]).parent / manifest["shards"][0]["path"]
        shard.write_bytes(shard.read_bytes() + b"tampered")
        with self.assertRaisesRegex(exporter.ExportError, "Shard hash/size mismatch"):
            exporter.verify_bundle(result["manifest"])

    def test_reflected_credential_in_base64_and_raw_headers_are_rejected(self):
        response = {"body_base64": base64.b64encode(b"credential: synthetic-private-key").decode()}
        self.write("calls/" + self.call_id + "/response.json", response)
        with self.assertRaisesRegex(exporter.ExportError, "Credential detected"):
            self.export(secrets=("synthetic-private-key",))
        self.write("calls/" + self.call_id + "/response.json", {"headers": {}, "json": {}})
        with self.assertRaisesRegex(exporter.ExportError, "HTTP headers"):
            self.export("header-bundle")

    def test_compact_result_requires_matching_retained_response(self):
        self.write("calls/" + self.call_id + "/response.json", {"http_status": 500, "json": {}})
        with self.assertRaisesRegex(exporter.ExportError, "Result response differs"):
            self.export()

    def test_unpack_never_overwrites_existing_destination(self):
        result = self.export()
        destination = self.root / "already-exists"
        destination.mkdir()
        sentinel = destination / "keep.txt"
        sentinel.write_bytes(b"keep")
        with self.assertRaisesRegex(exporter.ExportError, "already exists"):
            exporter.verify_bundle(result["manifest"], destination)
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_omitted_derived_mode_has_exact_completion_header_and_vector_slots(self):
        vector = [float(i) for i in range(70000)]  # Large synthetic value crosses reader buffers.
        record = {"trace_id": self.call_id, "status": "completed", "other": "preserved",
                  "embeddings": {"baai/bge-m3": [{"start": 0, "end": 16, "text": "fixture",
                                                   "input_sha256": "fixture-hash", "vector": vector}]}}
        original = {"embedding_model": "baai/bge-m3", "records": [record],
                    "scientific_validity": "not_assessed", "word_chunk_size": 16}
        self.write("baai_bge-m3-embedded.json", original)
        result = self.export()
        destination = self.root / "restored-derived"
        exporter.verify_bundle(result["manifest"], destination)
        self.assertFalse((destination / "state/baai_bge-m3-embedded.json").exists())
        registry = json.loads((destination / "bundle/derived-embedding-files.json").read_bytes())
        entry, absent = registry["files"]
        self.assertTrue(entry["file_present"])
        self.assertFalse(absent["file_present"])
        restored_record = entry["records"][0]["record"]
        self.assertEqual(restored_record["other"], "preserved")
        self.assertNotIn("vector", restored_record["embeddings"]["baai/bge-m3"][0])
        slot = entry["records"][0]["vector_slots"][0]
        self.assertEqual(slot["dimension"], len(vector))
        self.assertEqual(slot["vector_sha256"], exporter.sha(exporter.encoded(vector)))
        restored_record["embeddings"][slot["model"]][slot["segment_index"]]["vector"] = vector
        reconstructed = dict(entry["header"], records=[restored_record])
        self.assertEqual(exporter.sha(exporter.encoded(reconstructed)), entry["original_sha256"])

    def test_bound_source_bytes_must_match_the_inventory(self):
        self.write("source-inventory.json", {"files": {"resumption/runner.py": "0" * 64}})
        with self.assertRaisesRegex(exporter.ExportError, "Frozen source snapshot"):
            self.export()

    def test_capture_compaction_preserves_nonascii_floats_and_result_exactly(self):
        payload = {"model": "fixture", "text": "проверка Unicode", "vector": [0.25, -0.0, 1.3e-8]}
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        response = {"http_status": 200, "body_base64": base64.b64encode(raw).decode(),
                    "body_sha256": exporter.sha(raw), "body_storage": "original_bytes",
                    "raw_body": raw.decode("utf-8"), "json": payload, "elapsed_seconds": 0.125}
        self.write("calls/" + self.call_id + "/response.json", response)
        self.write("calls/" + self.call_id + "/result.json", {"call_id": self.call_id, "response": response})
        original_response = (self.call / "response.json").read_bytes()
        original_result = (self.call / "result.json").read_bytes()
        result = self.export()
        manifest = json.loads(Path(result["manifest"]).read_bytes())
        row = next(row for row in manifest["files"] if row["path"].endswith("/response.json"))
        self.assertEqual(row["transformation"]["kind"], "omit_capture_decoded_copies")
        self.assertLess(row["stored_bytes"], row["original_bytes"])
        destination = self.root / "capture-restored"
        exporter.verify_bundle(result["manifest"], destination)
        restored = destination / "state/calls" / self.call_id
        self.assertEqual((restored / "response.json").read_bytes(), original_response)
        self.assertEqual((restored / "result.json").read_bytes(), original_result)
        self.assertEqual((self.call / "response.json").read_bytes(), original_response)

    def test_noncanonical_or_invalid_utf8_capture_remains_verbatim(self):
        examples = [
            {"http_status": 200, "body_base64": base64.b64encode(b"{}").decode(), "raw_body": "{}", "json": {}},
            {"http_status": 200, "body_base64": base64.b64encode(b"\xff").decode(), "raw_body": None, "json": {}},
        ]
        for index, response in enumerate(examples):
            with self.subTest(index=index):
                self.write("calls/" + self.call_id + "/response.json", response)
                self.write("calls/" + self.call_id + "/result.json", {"call_id": self.call_id, "response": response})
                if index == 0:
                    with (self.call / "response.json").open("ab") as source:
                        source.write(b"\n")
                original = (self.call / "response.json").read_bytes()
                result = self.export("verbatim-" + str(index))
                manifest = json.loads(Path(result["manifest"]).read_bytes())
                row = next(row for row in manifest["files"] if row["path"].endswith("/response.json"))
                self.assertNotIn("transformation", row)
                self.assertEqual(row["stored_sha256"], exporter.sha(original))


if __name__ == "__main__":
    unittest.main()
