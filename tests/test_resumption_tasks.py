"""Corpus grouping and independent feasibility checks, without model calls."""
from collections import Counter, defaultdict
import unittest

from resumption.generator_audit import solve_reference, verify_answer, witness_text
from resumption.tasks import build


class ResumptionCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = build()

    def test_paired_roots_and_disjoint_admissions(self):
        tasks = self.document["tasks"]
        roots = defaultdict(list)
        for task in tasks:
            roots[task["root_id"]].append(task)
        self.assertEqual(len(tasks), 96)
        self.assertEqual(len(roots), 48)
        self.assertTrue(all(len(rows) == 2 for rows in roots.values()))
        self.assertTrue(all(len({r["split"] for r in rows}) == 1 for rows in roots.values()))
        self.assertFalse(set(roots) & {r["root_id"] for r in self.document["admission_tasks"]})
        self.assertEqual(Counter(t["split"] for t in tasks), {"train": 48, "validation": 16, "test": 32})
        self.assertEqual(len({t["instance_sha256"] for t in tasks + self.document["admission_tasks"]}), 100)

    def test_reference_witnesses_and_search_pair_balance(self):
        pairs = defaultdict(list)
        for task in self.document["tasks"]:
            verdict = verify_answer(task, witness_text(task))
            self.assertEqual(verdict["verdict"], "correct")
            if task["domain"] != "math":
                answer = solve_reference(task)
                pairs[task["root_id"]].append(answer != "IMPOSSIBLE" and answer != "UNSAT")
        self.assertTrue(all(sorted(values) == [False, True] for values in pairs.values()))


if __name__ == "__main__":
    unittest.main()
