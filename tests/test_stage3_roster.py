"""The §5.5 roster is registered and unexecuted. It is not an E0 result."""
import json
from pathlib import Path
import unittest

from measurement.core import digest, split_manifest
from stage3.roster import ROSTER_PATH, VERSION, build_document, historical_ids, mint, validate

ROOT = Path(__file__).resolve().parents[1]


class PilotRosterTests(unittest.TestCase):
    def test_committed_roster_matches_builder_and_excludes_confirmatory(self):
        document = json.loads(ROSTER_PATH.read_bytes())
        result = validate(document)
        self.assertEqual(result["status"], "preregistered_not_executed")
        self.assertEqual(result["tasks"], 200)
        self.assertEqual(result["roots"], 12)
        self.assertFalse(result["stage3_started"])
        self.assertEqual(document["starter_design"]["trace_upper_bound"], 1800)
        self.assertEqual(document["stratum_counts_per_domain"], {"easy": 17, "medium": 17, "hard": 16})
        self.assertTrue(all(row["split"] == "development" for row in document["split_manifest"]["tasks"]))
        self.assertEqual(build_document()["roster_sha256"], document["roster_sha256"])

    def test_historical_stage0_roots_stay_disjoint(self):
        document = json.loads(ROSTER_PATH.read_bytes())
        tasks, roots, prompts = historical_ids()
        self.assertFalse(tasks & {task["task_id"] for task in document["tasks"]})
        self.assertFalse(roots & {task["root_id"] for task in document["tasks"]})
        self.assertFalse(prompts & {row["prompt_sha256"] for row in document["split_manifest"]["tasks"]})

    def test_unforced_hash_bucket_can_be_confirmatory_but_roster_is_not(self):
        root = next(
            candidate for index in range(10000)
            if (bucket := int(digest([VERSION, candidate := f"leak-probe-{index}"])[:16], 16) % 100) >= 80
        )
        leaked = split_manifest(
            [{"task_id": "leak", "root_id": root, "domain": "math", "generator_id": "probe", "prompt": "Probe leak."}],
            seed=VERSION,
        )
        self.assertEqual(leaked["tasks"][0]["split"], "confirmatory")
        sealed = mint("math", "easy", 0)
        self.assertTrue(sealed["confirmatory_excluded"])
        self.assertEqual(split_manifest([sealed], seed=VERSION)["tasks"][0]["split"], "development")

    def test_receipt_cannot_claim_a_live_pilot(self):
        document = json.loads(ROSTER_PATH.read_bytes())
        document["paid_calls"] = 1
        with self.assertRaisesRegex(ValueError, "live run"):
            validate(document)
        document = json.loads(ROSTER_PATH.read_bytes())
        document["E0"] = "passed"
        with self.assertRaisesRegex(ValueError, "passes E0"):
            validate(document)
