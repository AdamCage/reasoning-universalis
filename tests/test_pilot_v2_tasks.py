"""Offline checks of development roots, independent references and leakage guards."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest

from pilot_v2 import tasks as p


def fixture(domain, data):
    task = {"domain": domain, "data": data, "generator_version": p.VERSION}
    task["instance_sha256"] = p.exact_instance_key(task)
    task["reference_certificate"] = p.reference_certificate(task)
    task["reference_certificate_sha256"] = p.digest(task["reference_certificate"])
    task["task_digest"] = p.digest(task)
    return task


class DevelopmentTasksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = p.load_legacy_inventory()
        cls.document = p.build_development(legacy=cls.legacy, holdout_commitment="a" * 64)
        cls.tasks = cls.document["tasks"]

    def test_development_design_and_dependent_roots(self):
        self.assertEqual(len(self.tasks), 48)
        roots = defaultdict(list)
        for task in self.tasks:
            roots[task["root_id"]].append(task)
            self.assertEqual(task["split"], "development")
            self.assertEqual(task["forced_split"], "development")
            self.assertTrue(task["confirmatory_excluded"])
            self.assertNotIn("output_budget", task)
            self.assertNotIn("max_tokens", task["data"])
        self.assertEqual(len(roots), 24)
        for members in roots.values():
            self.assertEqual({t["variant_index"] for t in members}, {0, 1})
            self.assertEqual(members[0]["structural_fingerprint"], members[1]["structural_fingerprint"])
            self.assertNotEqual(members[0]["prompt"], members[1]["prompt"])
        self.assertEqual(Counter(t["domain"] for t in self.tasks), {d: 12 for d in p.DOMAINS})
        self.assertEqual(Counter(t["tier"] for t in self.tasks), {t: 16 for t in p.TIERS})

    def test_all_witnesses_and_independent_certificates(self):
        for task in self.tasks:
            with self.subTest(task=task["task_id"]):
                self.assertTrue(p.verify_certificate(task, task["reference_certificate"]))
                result = p.verify_answer(task, p.witness_text(task))
                self.assertEqual(result["verdict"], "correct")
                self.assertTrue(result["gradable"])

    def test_difficulty_is_observed_work_and_not_inference_budget(self):
        for task in self.tasks:
            sizes = p.LIMITS[task["domain"]][p.TIERS.index(task["tier"])]
            complexity = task["complexity"]
            if task["domain"] == "math":
                self.assertEqual(complexity["arithmetic_operations"], 3 * sizes["operations_per_track"])
            elif task["domain"] == "logic":
                self.assertEqual(complexity["exhaustive_assignment_bound"], 2 ** sizes["variables"])
            elif task["domain"] == "algorithms":
                self.assertEqual(complexity["nodes"], sizes["nodes"])
                self.assertEqual(complexity["edges"], sizes["edges"])
            else:
                self.assertEqual(complexity["cells"], sizes["width"] ** 2)
                self.assertEqual(complexity["obstacles"], sizes["obstacles"])

    def test_explicit_arithmetic_oracle_and_signed_answer(self):
        task = fixture("math", {"tracks": [
            {"initial": 7, "steps": [["mul", 3], ["sub", 2]], "weight": 1},
            {"initial": 8, "steps": [["add", 4], ["mul", 2]], "weight": -1},
            {"initial": 11, "steps": [["add", 8], ["mul", 3]], "weight": 1}]})
        self.assertEqual(p.solve_reference(task), 52)
        self.assertTrue(p.verify_certificate(task, task["reference_certificate"]))
        self.assertTrue(p.verify_answer(task, "work\nANSWER: +52\n")["correct"])
        self.assertFalse(p.verify_answer(task, "ANSWER: 53")["correct"])
        for text in ("ANSWER: 52.0", "ANSWER: true", "ANSWER: ５２", "52", None):
            self.assertEqual(p.verify_answer(task, text)["verdict"], "unparseable")

    def test_cnf_exhaustive_sat_unsat_and_witness(self):
        for clauses, answer, count in (([[1, 2], [-1, 2]], "SAT", 2), ([[1], [-1]], "UNSAT", 0)):
            task = fixture("logic", {"variables": 2, "clauses": clauses})
            self.assertEqual(p.solve_reference(task), answer)
            self.assertEqual(task["reference_certificate"]["satisfying_assignments"], count)
            self.assertTrue(p.verify_certificate(task, task["reference_certificate"]))
            changed = deepcopy(task["reference_certificate"])
            changed["truth_table_sha256"] = "0" * 64
            self.assertFalse(p.verify_certificate(task, changed))
        with self.assertRaises(ValueError):
            p.reference_certificate({"domain": "logic", "data": {"variables": 15, "clauses": []}})

    def test_small_topological_reference_against_all_permutations(self):
        rng = random.Random(318)
        for trial in range(15):
            edges = rng.sample([(a, b) for a in range(6) for b in range(6) if a != b], trial)
            task = fixture("algorithms", {"nodes": 6, "edges": edges})
            orders = [list(order) for order in itertools.permutations(range(6))
                      if all(order.index(a) < order.index(b) for a, b in edges)]
            expected = min(orders) if orders else "IMPOSSIBLE"
            self.assertEqual(p.solve_reference(task), expected)
            self.assertTrue(p.verify_certificate(task, task["reference_certificate"]))

    def test_lexicographic_order_strict_integer_parser(self):
        task = fixture("algorithms", {"nodes": 3, "edges": [[0, 2]]})
        self.assertEqual(p.solve_reference(task), [0, 1, 2])
        self.assertEqual(p.verify_answer(task, "ANSWER: [1,0,2]")["verdict"], "incorrect")
        for text in ("ANSWER: [false,1,2]", "ANSWER: [0.0,1,2]", "ANSWER: null"):
            self.assertEqual(p.verify_answer(task, text)["verdict"], "unparseable")

    def test_cycle_perturbations_preserve_impossibility(self):
        base = {"nodes": 5, "edges": [[0, 1], [1, 2], [2, 0], [3, 4]]}
        key = p.structural_fingerprint({"domain": "algorithms", "data": base})
        for member in range(2):
            data = p._perturb("algorithms", base, random.Random(member), member)
            task = fixture("algorithms", data)
            self.assertEqual(p.solve_reference(task), "IMPOSSIBLE")
            self.assertTrue(p.verify_certificate(task, task["reference_certificate"]))
            self.assertEqual(p.structural_fingerprint(task), key)
            bad = deepcopy(task["reference_certificate"])
            bad["cycle"] = [3, 4, 3]
            self.assertFalse(p.verify_certificate(task, bad))

    def test_grid_references_disconnected_and_over_budget(self):
        examples = [
            ({"width": 3, "height": 3, "start": [0, 0], "goal": [2, 2],
              "obstacles": [[1, 0], [1, 1], [1, 2]], "max_steps": 8}, None),
            ({"width": 3, "height": 3, "start": [0, 0], "goal": [2, 2],
              "obstacles": [], "max_steps": 3}, 4)]
        for data, distance in examples:
            task = fixture("planning", data)
            self.assertEqual(p.solve_reference(task), "IMPOSSIBLE")
            self.assertEqual(task["reference_certificate"]["shortest_distance"], distance)
            self.assertTrue(p.verify_certificate(task, task["reference_certificate"]))
            self.assertFalse(p.verify_answer(task, 'ANSWER: ["E","E","S","S"]')["correct"])

    def test_grid_rotation_reflection_and_absolute_directions(self):
        base = {"width": 4, "height": 3, "start": [0, 0], "goal": [3, 2],
                "obstacles": [[1, 0], [1, 1]], "max_steps": 7}
        original = fixture("planning", base)
        for reflection in (False, True):
            for rotation in range(4):
                task = fixture("planning", p.grid_transform(base, rotation, reflection))
                self.assertEqual(task["reference_certificate"]["shortest_distance"], 5)
                self.assertEqual(p.structural_fingerprint(task), p.structural_fingerprint(original))
                self.assertTrue(p.verify_answer(task, p.witness_text(task))["correct"])
                self.assertTrue(p.verify_certificate(task, task["reference_certificate"]))
        self.assertFalse(p._valid_plan(base, ["E"] * 3 + ["S"] * 2))
        self.assertFalse(p._valid_plan(base, ["N"]))

    def test_certificate_tampering_is_rejected_in_each_domain(self):
        for domain in p.DOMAINS:
            task = next(t for t in self.tasks if t["domain"] == domain)
            changed = deepcopy(task["reference_certificate"])
            changed["instance_sha256"] = "0" * 64
            self.assertFalse(p.verify_certificate(task, changed))
            changed = deepcopy(task["reference_certificate"])
            if domain == "math": changed["track_values"][0][0] += 1
            elif domain == "logic": changed["satisfying_assignments"] += 1
            elif domain == "algorithms": changed["critical_path_nodes"] += 1
            else: changed["reachable_cells"] += 1
            self.assertFalse(p.verify_certificate(task, changed))

    def test_task_and_reference_provenance_tampering_fails(self):
        for field in ("prompt", "instance_sha256", "reference_certificate_sha256", "generator_version"):
            changed = deepcopy(self.tasks[0])
            changed[field] = "tampered"
            with self.assertRaises(ValueError): p.verify_answer(changed, p.witness_text(self.tasks[0]))

    def test_legacy_inventory_covers_published_inputs_and_missingness(self):
        self.assertEqual(self.legacy.rows, 7466)
        self.assertEqual(len(self.legacy.sources), 11)
        self.assertGreater(self.legacy.unsupported_structural["missing_problem_data"], 0)
        self.assertTrue(any(row["path"].endswith("instances.jsonl.gz") for row in self.legacy.sources))
        for task in self.tasks:
            self.assertNotIn(task["instance_sha256"], self.legacy.exact)
            self.assertNotIn(task["structural_fingerprint"], self.legacy.structural)
            self.assertNotIn(p.normalized_prompt_key(task["prompt"]), self.legacy.prompts)

    def test_root_fingerprints_do_not_cross_roots(self):
        fingerprints = defaultdict(set)
        exact = defaultdict(set)
        for task in self.tasks:
            fingerprints[task["structural_fingerprint"]].add(task["root_id"])
            exact[task["instance_sha256"]].add(task["root_id"])
        self.assertEqual(len(fingerprints), 24)
        self.assertTrue(all(len(roots) == 1 for roots in fingerprints.values()))
        self.assertTrue(all(len(roots) == 1 for roots in exact.values()))

    def test_normalized_exact_and_relabeling_structural_flags(self):
        a = {"domain": "algorithms", "data": {"nodes": 4, "edges": [[0, 1], [1, 2], [0, 1]]}}
        b = {"domain": "algorithms", "data": {"nodes": 4, "edges": [[1, 2], [0, 1]]}}
        c = {"domain": "algorithms", "data": {"nodes": 4, "edges": [[3, 2], [2, 1]]}}
        self.assertEqual(p.exact_instance_key(a), p.exact_instance_key(b))
        self.assertNotEqual(p.exact_instance_key(a), p.exact_instance_key(c))
        self.assertEqual(p.structural_fingerprint(a), p.structural_fingerprint(c))
        self.assertEqual(p.normalized_prompt_key(" A  B\nC "), p.normalized_prompt_key("a b c"))

    def test_holdout_commitment_only_and_no_holdout_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            seed = Path(directory) / "private.bin"
            commitment = p.reserve_holdout(seed)
            self.assertEqual(seed.stat().st_size, 32)
            self.assertEqual(commitment, p.reserve_holdout(seed))
            self.assertEqual(commitment, hashlib.sha256(b"pilot-v2-fresh-holdout-v1\0" + seed.read_bytes()).hexdigest())
            self.assertNotIn(seed.read_bytes().hex(), json.dumps(self.document))
        self.assertEqual(self.document["holdout"]["status"], "seed_committed_tasks_not_generated")
        for seed in ("holdout", "confirmatory", "", None):
            with self.assertRaises(ValueError): p.build_development(seed, legacy=p.LegacyIndex(), holdout_commitment="a" * 64)
        with self.assertRaises(ValueError): p.build_development(legacy=p.LegacyIndex())

    def test_corpus_digest_and_deterministic_rebuild(self):
        content = {key: value for key, value in self.document.items() if key != "corpus_sha256"}
        self.assertEqual(self.document["corpus_sha256"], p.digest(content))
        rebuilt = p.build_development(legacy=self.legacy, holdout_commitment="a" * 64)
        self.assertEqual(p.canonical(self.document), p.canonical(rebuilt))


if __name__ == "__main__":
    unittest.main()
