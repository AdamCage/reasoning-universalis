"""Stage 3 offline pilot preparation. No paid call and no E0 pass."""
import json
from pathlib import Path
import unittest

from stage3.baseline_audit import surface_audit
from stage3.e0_offline import run
from stage3.pipeline import ALLOWLIST_PATH, verify_published_ledger
from stage3.pre_dispatch import plan
from stage3.roster_v3 import ROSTER_V3_PATH
from stage3.roster_v4 import ROSTER_V4_PATH, validate

ROOT = Path(__file__).resolve().parents[1]


class PreDispatchTests(unittest.TestCase):
    def test_positive_allowlist_excludes_the_unverified_models(self):
        routes = json.loads(ALLOWLIST_PATH.read_bytes())["routes"]
        models = {route["model_id"] for route in routes}
        self.assertNotIn("qwen/qwen3-32b", models)
        self.assertNotIn("deepseek/deepseek-v4.1-flash", models)
        self.assertTrue(all(route["admitted"] is True and route["long_trace_admitted"] is False for route in routes))
        ledger = verify_published_ledger()
        self.assertEqual(ledger["rows"], 32)
        self.assertEqual(ledger["charged_or_reserved_rub"], "246.7988793802352")

    def test_v3_surface_leak_is_closed_in_v4_without_replacing_v3(self):
        v3 = json.loads(ROSTER_V3_PATH.read_bytes())
        old = surface_audit(v3["tasks"])
        self.assertEqual(old["seed_parity_accuracy"], 1.0)
        self.assertGreater(old["prompt_length_accuracy"], 0.9)
        new = validate(json.loads(ROSTER_V4_PATH.read_bytes()))
        audit = new["surface_audit"]
        self.assertLessEqual(audit["seed_parity_accuracy"], 0.7)
        self.assertLessEqual(audit["prompt_length_accuracy"], 0.7)
        self.assertLessEqual(audit["structure_count_accuracy"], 0.7)
        self.assertLessEqual(audit["family_majority_accuracy"], 0.7)
        self.assertEqual(v3["roster_sha256"], "17f410cf6262adf7af6b58c5a7233cf4206e107463348213969fdb19ebe223eb")

    def test_e0_offline_and_admission_plan_do_not_pass_or_dispatch(self):
        report = run()
        self.assertEqual(report["status"], "not_passed")
        self.assertEqual(report["human_reference"], "not_completed")
        self.assertEqual(set(report["checks"]), {
            "synthetic_sequences_with_known_phases", "segmentation_accuracy", "state_recovery",
            "paraphrase_robustness", "style_and_length_robustness",
            "random_sequences_do_not_create_false_universality"})
        self.assertEqual(report["checks"]["random_sequences_do_not_create_false_universality"]["scrambled_exact_phase_recovery"], 0.0)
        packet = json.loads((ROOT / "design" / "HUMAN_REFERENCE_ITEMS.json").read_bytes())
        self.assertEqual(packet["status"], "awaiting_human_annotation")
        self.assertNotIn("constructed_phase", json.dumps(packet))
        gold = json.loads((ROOT / "design" / "HUMAN_REFERENCE_GOLD.json").read_bytes())
        self.assertEqual(gold["status"], "not_annotated")
        self.assertEqual(gold["labels"], [])
        admission = plan()
        self.assertFalse(admission["dispatched"])
        self.assertFalse(admission["models_admitted"])
        self.assertEqual(admission["request_count"], 48)
        self.assertEqual(len(admission["tasks"]), 8)
        self.assertTrue(all(model["admitted"] is False for model in admission["models"]))
