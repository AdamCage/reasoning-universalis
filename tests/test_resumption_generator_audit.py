"""Reference grading tests exercise algorithmic and trust-boundary failures."""
import copy
import json
import unittest

from resumption.generator_audit import (
    _components, canonical_instance_key, solve_reference, verify_answer, witness_text,
)
from stage2 import datasets
from stage3 import generators_v2, generators_v3, generators_v4


def fixture(domain, data, family="fixture"):
    return {"generator_version": "resumption-generators-v1", "domain": domain,
            "family": family, "data": data}


class ReferenceGradingTests(unittest.TestCase):
    def test_independent_witnesses_all_published_generator_schemas(self):
        tasks = [datasets.generate(domain, 0, level)
                 for domain in datasets.DOMAINS for level in ("easy", "medium", "hard")]
        for module in (generators_v2, generators_v3, generators_v4):
            tasks.extend(module.generate(domain, family, level, 0)
                         for domain, families in module.FAMILIES.items()
                         for family in families for level in ("easy", "medium", "hard"))
        for task in tasks:
            with self.subTest(version=task["generator_version"], domain=task["domain"],
                              family=task.get("family"), level=task["difficulty"]):
                self.assertEqual(verify_answer(task, witness_text(task))["verdict"], "correct")
                self.assertNotEqual(verify_answer(task, "ANSWER: garbage")["verdict"], "correct")

    def test_topological_reference_finds_lexicographic_answer_and_rejects_bool(self):
        task = fixture("algorithms", {"nodes": 3, "edges": [[2, 0]]})
        self.assertEqual(solve_reference(task), [1, 2, 0])
        self.assertEqual(verify_answer(task, "ANSWER: [1, 2, 0]")["verdict"], "correct")
        self.assertEqual(verify_answer(task, "ANSWER: [true, 2, 0]")["verdict"], "unparseable")
        self.assertEqual(verify_answer(task, "ANSWER: [2, 1, 0]")["verdict"], "incorrect")
        cyclic = fixture("algorithms", {"nodes": 2, "edges": [[0, 1], [1, 0]]})
        self.assertEqual(solve_reference(cyclic), "IMPOSSIBLE")

    def test_planning_checks_budget_obstacles_direction_and_complete_plan(self):
        task = fixture("planning", {"width": 3, "height": 2, "start": [0, 0],
                       "goal": [2, 1], "obstacles": [[1, 0]], "max_steps": 3})
        self.assertEqual(verify_answer(task, 'ANSWER: ["S","E","E"]')["verdict"], "correct")
        self.assertEqual(verify_answer(task, 'ANSWER: ["E","S","E"]')["verdict"], "incorrect")
        self.assertEqual(verify_answer(task, 'ANSWER: ["N","E","E"]')["verdict"], "incorrect")
        self.assertEqual(verify_answer(task, 'ANSWER: ["S","E"]')["verdict"], "incorrect")
        self.assertEqual(verify_answer(task, 'ANSWER: {"plan":["S","E","E"]}')["verdict"], "unparseable")
        limited = copy.deepcopy(task)
        limited["data"]["max_steps"] = 2
        self.assertEqual(solve_reference(limited), "IMPOSSIBLE")
        self.assertEqual(verify_answer(limited, 'ANSWER: ["S","E","E"]')["verdict"], "incorrect")
        self.assertEqual(verify_answer(limited, "ANSWER: IMPOSSIBLE")["verdict"], "correct")

    def test_strict_marker_and_integer_answer(self):
        task = fixture("math", {"start": 3, "steps": [["mul", 2], ["sub", 1]]}, "fixed_fold")
        self.assertEqual(verify_answer(task, "work\nANSWER: 5")["verdict"], "correct")
        for text in ("5", "ANSWER: 5\nmore text", "ANSWER: 5.0", "ANSWER: true", ""):
            self.assertEqual(verify_answer(task, text)["verdict"], "unparseable")

    def test_normalized_instance_group_ignores_only_irrelevant_order_and_metadata(self):
        a = fixture("logic", {"family": "a", "variables": 2,
                    "clauses": [[1, -2], [2]]})
        b = fixture("logic", {"family": "b", "variables": 2,
                    "clauses": [[2], [-2, 1], [2]]})
        b.update(seed=999, root_id="unrelated")
        self.assertEqual(canonical_instance_key(a), canonical_instance_key(b))
        b["data"]["clauses"][0] = [-2]
        self.assertNotEqual(canonical_instance_key(a), canonical_instance_key(b))

    def test_unknown_version_is_not_silently_a_model_failure(self):
        task = fixture("logic", {"variables": 1, "clauses": [[1]]})
        task["generator_version"] = "not-registered"
        with self.assertRaises(ValueError):
            verify_answer(task, "ANSWER: SAT")

    def test_real_seed_renaming_does_not_create_new_independent_instance(self):
        a = generators_v4.generate("math", "fixed_fold", "hard", 0)
        b = generators_v4.generate("math", "fixed_fold", "hard", 7)
        self.assertNotEqual(a["root_id"], b["root_id"])
        self.assertEqual(a["prompt"], b["prompt"])
        self.assertEqual(canonical_instance_key(a), canonical_instance_key(b))
        self.assertEqual(len(set(_components([a, b]))), 1)

    def test_real_v4_valid_arithmetic_is_not_compatible_with_v2_scorer(self):
        task = generators_v4.generate("math", "fixed_fold", "hard", 0)
        text = witness_text(task)
        self.assertEqual(generators_v2.verify(task, text)["verdict"], "unparseable")
        self.assertEqual(verify_answer(task, text)["verdict"], "correct")

    def test_complementary_target_pair_never_crosses_dependency_groups(self):
        a = generators_v4.generate("logic", "cnf_a", "easy", 0)
        b = generators_v4.generate("logic", "cnf_a", "easy", 1)
        self.assertNotEqual(canonical_instance_key(a), canonical_instance_key(b))
        self.assertEqual(len(set(_components([a, b]))), 2)
        self.assertEqual(len(set(_components([a, b], include_design_pairs=True))), 1)


if __name__ == "__main__":
    unittest.main()
