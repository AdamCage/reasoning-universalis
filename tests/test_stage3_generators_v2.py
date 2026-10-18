"""Stage 3 families must defeat the trivial baselines named in the Stage 2 review."""
import json
from pathlib import Path
import unittest

from stage3.generators_v2 import FAMILIES, generate, verify, witness
from stage3.roster_v2 import ROSTER_V2_PATH, build_document, validate

ROOT = Path(__file__).resolve().parents[1]


def answer(task, text):
    return verify(task, "ANSWER: " + text)["verdict"] == "correct"


class GeneratorV2Tests(unittest.TestCase):
    def test_every_family_has_an_independent_witness_and_rejects_garbage(self):
        for domain, families in FAMILIES.items():
            for family in families:
                for difficulty in ("easy", "medium", "hard"):
                    task = generate(domain, family, difficulty, 0)
                    self.assertEqual(verify(task, witness(task))["verdict"], "correct")
                    self.assertNotEqual(verify(task, "ANSWER: not-a-solution")["verdict"], "correct")
                    self.assertNotIn("\nANSWER:", task["prompt"])

    def test_registered_roster_breaks_sat_and_identity_baselines(self):
        document = json.loads(ROSTER_V2_PATH.read_bytes())
        result = validate(document)
        self.assertEqual(result["roots"], 200)
        self.assertLessEqual(result["logic_sat_count"] / 50, 0.45)
        self.assertGreaterEqual(result["logic_sat_count"] / 50, 0.25)
        self.assertEqual(document["identity_topo_baseline_correct"], 0)
        self.assertFalse(document["mass_pilot_authorized"])
        logic = [task for task in document["tasks"] if task["domain"] == "logic"]
        self.assertLessEqual(sum(answer(task, "SAT") for task in logic) / len(logic), 0.45)
        math_tasks = [task for task in document["tasks"] if task["domain"] == "math"]
        trivial = 0
        for task in math_tasks:
            if task["family"] == "operation_chain":
                trivial += answer(task, str(task["data"]["start"]))
            elif task["family"] == "two_moduli":
                trivial += answer(task, str(task["data"]["residue_a"]))
            else:
                coefficient = task["data"]["coefficients"]
                trivial += answer(task, str(coefficient["a"] + coefficient["b"]))
        self.assertLess(trivial / len(math_tasks), 0.35)
        self.assertEqual(build_document()["roster_sha256"], document["roster_sha256"])

    def test_v1_roster_remains_the_development_artifact(self):
        v1 = json.loads((ROOT / "design" / "PILOT_SECTION_5_5_ROSTER.json").read_bytes())
        v2 = json.loads(ROSTER_V2_PATH.read_bytes())
        self.assertEqual(v1["root_count"], 12)
        self.assertEqual(v1["roster_sha256"], v2["superseded_roster_sha256"])
        self.assertTrue(v1["stage3_started"] is False)
