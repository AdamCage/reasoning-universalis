"""Guards sit on the Stage 3 path, and v3 is harder to guess from the family name."""
import json
from pathlib import Path
import unittest

from measurement.core import text_hash
from stage3.baseline_audit import summarize
from stage3.bindings import embedding_texts
from stage3.pipeline import accept_embeddings, execute_attempt
from stage3.roster_v3 import ROSTER_V3_PATH, validate

ROOT = Path(__file__).resolve().parents[1]
LEDGER = "e062d9bdd228933ddcca0047d9ee15e564b82413bf88f92c5d06550c9febb88d"


def segment(segment_id, position, text, start):
    return {"segment_id": segment_id, "trace_id": "t", "measurement_config_digest": "cfg",
            "position": position, "text": text, "char_start": start, "char_end": start + len(text),
            "trace_sha256": "trace"}


class PipelineTests(unittest.TestCase):
    def test_contextual_embedding_uses_the_full_registered_input(self):
        rows = [segment("a", 0, "Plan.", 0), segment("b", 1, "Check.", 5)]
        texts = embedding_texts(rows, "Contextual")
        self.assertEqual(texts[1], "Plan.Check.")
        records = [{"segment_id": row["segment_id"], "model_id": "baai/bge-m3",
                    "input_sha256": text_hash(text), "trace_sha256": "trace", "vector": [1.0] * 1024}
                   for row, text in zip(rows, texts)]
        self.assertEqual(len(accept_embeddings(rows, records, "baai/bge-m3", 1024, "Contextual")), 2)
        records[1]["input_sha256"] = text_hash(rows[1]["text"])
        with self.assertRaisesRegex(ValueError, "Contextual"):
            accept_embeddings(rows, records, "baai/bge-m3", 1024, "Contextual")

    def test_dispatch_checks_admission_ledger_and_status_before_analysis(self):
        import tempfile
        from decimal import Decimal
        calls = []

        def transport(request):
            calls.append(request)
            return {"http_status": 200, "json": {"model": request["model"], "provider": "reviewed", "id": "gen",
                             "choices": [{"finish_reason": "stop", "message": {"reasoning": "Plan.", "content": "4"}}]}}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.json"
            ledger.write_text("[]", encoding="utf-8")
            allowlist = root / "allow.json"
            allowlist.write_text(json.dumps({"routes": [
                {"model_id": "openai/gpt-oss-20b", "provider_id": "reviewed", "purpose": "fixture", "admitted": True}
            ]}), encoding="utf-8")
            common = dict(task_prompt="Q", transport=transport, ledger_path=ledger, journal_root=root / "journal",
                          cap_rub=Decimal("10"), prompt_per_token="0.000001", completion_per_token="0.000002",
                          purpose="fixture", allowlist_path=allowlist,
                          expected_ledger_sha256=__import__("hashlib").sha256(ledger.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, "positive admission"):
                execute_attempt(model_id="qwen/qwen3-32b", task_id="t", sample_index=0, seed=1,
                                provider_id="proposed", protocol_digest="abc", **common)
            self.assertEqual(calls, [])
            before = ledger.read_bytes()
            def fail(_request):
                raise RuntimeError("down")
            with self.assertRaises(RuntimeError):
                execute_attempt(model_id="openai/gpt-oss-20b", task_id="t", sample_index=0, seed=1,
                                provider_id="reviewed", protocol_digest="abc",
                                **{**common, "transport": fail, "expected_ledger_sha256": __import__("hashlib").sha256(before).hexdigest()})
            pending = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(pending[0]["state"], "pending")
            self.assertTrue(any(path.is_file() for path in (root / "journal" / "raw").iterdir()))
            with self.assertRaisesRegex(ValueError, "Mass pilot"):
                execute_attempt(model_id="openai/gpt-oss-20b", task_id="t", sample_index=1, seed=3,
                                provider_id="reviewed", protocol_digest="abc", mass_pilot=True,
                                **{**common, "expected_ledger_sha256": __import__("hashlib").sha256(ledger.read_bytes()).hexdigest()})
            record = execute_attempt(model_id="openai/gpt-oss-20b", task_id="t", sample_index=1, seed=3,
                                     provider_id="reviewed", protocol_digest="abc",
                                     **{**common, "expected_ledger_sha256": __import__("hashlib").sha256(ledger.read_bytes()).hexdigest()})
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["http_status"], 200)
            self.assertTrue(record["analysis_usable"])
            self.assertEqual(calls[0]["model"], "openai/gpt-oss-20b")
            self.assertEqual(calls[0]["seed"], 3)
            with self.assertRaisesRegex(ValueError, "disagrees"):
                execute_attempt(model_id="openai/gpt-oss-20b", task_id="t", sample_index=2, seed=4,
                                provider_id="reviewed", protocol_digest="abc", claimed_status="failed",
                                **{**common, "expected_ledger_sha256": __import__("hashlib").sha256(ledger.read_bytes()).hexdigest()})

    def test_v2_family_leak_is_measured_and_v3_is_not_family_determined(self):
        v2 = json.loads((ROOT / "design" / "PILOT_SECTION_5_5_ROSTER_V2.json").read_bytes())
        v3 = json.loads(ROSTER_V3_PATH.read_bytes())
        old = summarize(v2["tasks"])
        new = validate(v3)
        self.assertEqual(old["family_majority_accuracy"], 1)
        self.assertAlmostEqual(old["logic_always_unsat"], 0.66)
        self.assertLessEqual(new["family_majority_accuracy"], 0.6)
        self.assertLessEqual(new["logic_always_unsat"], 0.55)
        self.assertFalse(new["mass_pilot_authorized"])
