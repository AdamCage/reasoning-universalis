"""Offline guards requested before any paid Stage 3 run."""
import json
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
import unittest

from measurement.core import text_hash
from stage0.runner import Ledger, StopRun, rates
from stage3.attempt_status import assert_status_matches
from stage3.bindings import align_embeddings, require_trajectory_order
from stage3.evidence_audit import audit
from stage3.schedule import bind_response, freeze_attempt, refuse_dict_order_model

ROOT = Path(__file__).resolve().parents[1]


def segment(segment_id, position, text):
    return {"segment_id": segment_id, "trace_id": "t", "measurement_config_digest": "cfg",
            "position": position, "text": text, "char_start": position, "char_end": position + len(text),
            "trace_sha256": "trace"}


class GuardTests(unittest.TestCase):
    def test_shuffled_segments_and_unbound_embeddings_are_rejected(self):
        rows = [segment("a", 0, "Plan."), segment("b", 1, "Check.")]
        rows[1]["char_start"] = len(rows[0]["text"])
        rows[1]["char_end"] = rows[1]["char_start"] + len(rows[1]["text"])
        require_trajectory_order(rows)
        with self.assertRaisesRegex(ValueError, "trajectory order"):
            require_trajectory_order(list(reversed(rows)))
        records = [{"segment_id": row["segment_id"], "model_id": "baai/bge-m3",
                    "input_sha256": text_hash(row["text"]), "trace_sha256": row["trace_sha256"],
                    "vector": [0.0] * 1024} for row in reversed(rows)]
        aligned = align_embeddings(rows, records, "baai/bge-m3", 1024)
        self.assertEqual(len(aligned), 2)
        qwen = [{**record, "model_id": "qwen/qwen3-embedding-8b", "vector": [0.0] * 4096} for record in records]
        qwen[0]["vector"] = [0.0] * 8
        with self.assertRaisesRegex(ValueError, "dimension"):
            align_embeddings(rows, qwen, "qwen/qwen3-embedding-8b", 8)
        with self.assertRaisesRegex(ValueError, "dimension"):
            align_embeddings(rows, qwen, "qwen/qwen3-embedding-8b", 4096)

    def test_attempt_identity_is_explicit_and_status_cannot_hide_a_trace(self):
        spec = freeze_attempt(model_id="openai/gpt-oss-20b", task_id="task", sample_index=2,
                              seed=7, provider_id="reviewed", protocol_digest="abc")
        self.assertFalse(spec["dispatch"])
        self.assertTrue(spec["admitted_for_dispatch"])
        withheld = freeze_attempt(model_id="qwen/qwen3-32b", task_id="task", sample_index=0,
                                  seed=1, provider_id="proposed", protocol_digest="abc")
        self.assertFalse(withheld["admitted_for_dispatch"])
        with self.assertRaisesRegex(ValueError, "explicit"):
            freeze_attempt(model_id="", task_id="task", sample_index=0, seed=1,
                           provider_id="reviewed", protocol_digest="abc")
        with self.assertRaisesRegex(ValueError, "next"):
            refuse_dict_order_model()
        request = {"model": spec["model_id"], "seed": spec["seed"]}
        response = {"json": {"model": spec["model_id"], "provider": "other"}}
        with self.assertRaisesRegex(ValueError, "provider"):
            bind_response(spec, request, response)
        body = {"id": "gen", "choices": [{"finish_reason": "stop", "message": {"reasoning": "Plan.", "content": "4"}}]}
        with self.assertRaisesRegex(ValueError, "disagrees"):
            assert_status_matches({"status": "failed"}, 200, body)
        self.assertEqual(assert_status_matches({"status": "completed"}, 200, body), "completed")

    def test_unknown_cost_keeps_the_reservation_and_million_units_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text("[]", encoding="utf-8")
            ledger = Ledger(path, Decimal("10"))
            row = ledger.reserve(Decimal("1.5"), "fixture")
            ledger.finish(row, {"http_status": 200, "json": {}})
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsNone(saved[0]["reported_cost_rub"])
            self.assertEqual(saved[0]["charged_or_reserved_rub"], "1.5")
        with self.assertRaises(StopRun):
            rates({"json": {"data": {"endpoints": [{"pricing_units": {"prompt": "million", "completion": "token"},
                                                    "pricing": {"prompt": "0.2", "completion": "0.2"}}]}}})

    def test_rewritten_workflow_claim_fails_the_restored_audit(self):
        source = ROOT / "evidence" / "stage2-2026-10-14.zip"
        self.assertEqual(audit(source)["kernel_claim"], "restored")
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "tampered.zip"
            with zipfile.ZipFile(source) as original, zipfile.ZipFile(tampered, "w") as rebuilt:
                files = {name: original.read(name) for name in original.namelist()}
            workflow = json.loads(files["workflow-result.json"])
            workflow["claim"] = "0" * 32
            files["workflow-result.json"] = json.dumps(workflow).encode()
            manifest = json.loads(files["manifest.json"])
            import hashlib
            for row in manifest["files"]:
                if row["path"] == "workflow-result.json":
                    row["sha256"] = hashlib.sha256(files["workflow-result.json"]).hexdigest()
                    row["bytes"] = len(files["workflow-result.json"])
            files["manifest.json"] = json.dumps(manifest).encode()
            with zipfile.ZipFile(tampered, "w") as rebuilt:
                for name, data in files.items():
                    rebuilt.writestr(name, data)
            with self.assertRaisesRegex(ValueError, "not the restored kernel claim"):
                audit(tampered)
