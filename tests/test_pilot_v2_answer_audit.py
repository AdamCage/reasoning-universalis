"""Synthetic answer diagnostics only; no active model result files are opened."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from pilot_v2 import tasks as p
from scripts.audit_pilot_v2_answers import audit_document, classify, digest, parse_answer, check_task


def fixture(domain, data):
    task = {"task_id": "fixture", "root_id": "fixture-root", "domain": domain,
            "data": data, "generator_version": p.VERSION}
    task["instance_sha256"] = p.exact_instance_key(task)
    task["reference_certificate"] = p.reference_certificate(task)
    task["reference_certificate_sha256"] = digest(task["reference_certificate"])
    task["task_digest"] = digest(task)
    return task


class IndependentAnswerAuditTests(unittest.TestCase):
    def test_all_frozen_corpus_witnesses_pass_without_reading_model_outputs(self):
        path = Path(__file__).resolve().parents[1] / "artifacts/pilot-v2-2026-11-08/development-tasks.json"
        tasks = json.loads(path.read_bytes())["tasks"]
        self.assertEqual(len(tasks), 48)
        for task in tasks:
            with self.subTest(task=task["task_id"]):
                self.assertEqual(classify(task, p.witness_text(task))["verdict"], "correct")

    def test_arithmetic_oracle_and_strict_parser(self):
        task = fixture("math", {"tracks": [
            {"initial": 7, "steps": [["mul", 3], ["sub", 2]], "weight": 1},
            {"initial": 8, "steps": [["add", 4], ["mul", 2]], "weight": -1},
            {"initial": 11, "steps": [["add", 8], ["mul", 3]], "weight": 1}]})
        self.assertTrue(classify(task, "work\nANSWER: +52\n")["correct"])
        self.assertEqual(classify(task, "ANSWER: 53")["reason"], "wrong_exact_integer")
        for text in ("ANSWER: 52.0", "ANSWER: ５２", "52", "ANSWER: true", None):
            self.assertEqual(classify(task, text)["verdict"], "unparseable")

    def test_sat_and_unsat_certificates_decide_answers(self):
        sat = fixture("logic", {"variables": 2, "clauses": [[1, 2], [-1, 2]]})
        unsat = fixture("logic", {"variables": 2, "clauses": [[1], [-1]]})
        self.assertTrue(classify(sat, "ANSWER: SAT")["correct"])
        self.assertTrue(classify(unsat, "ANSWER: UNSAT")["correct"])
        self.assertEqual(classify(unsat, "ANSWER: SAT")["reason"], "contradicts_exhaustive_cnf_certificate")

    def test_nonlexicographic_and_dependency_violating_orders_are_distinct(self):
        task = fixture("algorithms", {"nodes": 3, "edges": [[0, 2]]})
        self.assertTrue(classify(task, "ANSWER: [0,1,2]")["correct"])
        self.assertEqual(classify(task, "ANSWER: [1,0,2]")["reason"], "valid_but_nonlexicographic_topological_order")
        self.assertEqual(classify(task, "ANSWER: [2,0,1]")["reason"], "violates_directed_dependency")
        self.assertEqual(classify(task, "ANSWER: [0,0,1]")["reason"], "wrong_node_permutation")
        for answer in ("ANSWER: [false,1,2]", "ANSWER: [0.0,1,2]"):
            self.assertEqual(classify(task, answer)["verdict"], "unparseable")

    def test_cycle_witness_rejects_proposed_order(self):
        task = fixture("algorithms", {"nodes": 3, "edges": [[0, 1], [1, 2], [2, 0]]})
        self.assertTrue(classify(task, "ANSWER: IMPOSSIBLE")["correct"])
        self.assertEqual(classify(task, "ANSWER: [0,1,2]")["reason"], "order_proposed_for_graph_with_checked_cycle")

    def test_bad_plans_have_concrete_reasons(self):
        task = fixture("planning", {"width": 3, "height": 3, "start": [0, 0], "goal": [2, 2],
                                   "obstacles": [[1, 0]], "max_steps": 4})
        cases = [('ANSWER: ["E","E","S","S"]', "plan_enters_obstacle"),
                 ('ANSWER: ["N"]', "plan_leaves_grid"),
                 ('ANSWER: ["S"]', "plan_does_not_reach_goal"),
                 ('ANSWER: ["S","S","E","E","W"]', "plan_exceeds_move_bound"),
                 ('ANSWER: IMPOSSIBLE', "claims_impossible_despite_checked_bounded_path")]
        for answer, reason in cases:
            self.assertEqual(classify(task, answer)["reason"], reason)
        self.assertTrue(classify(task, 'ANSWER: ["S","S","E","E"]')["correct"])

    def test_disconnected_grid_certificate(self):
        task = fixture("planning", {"width": 3, "height": 3, "start": [0, 0], "goal": [2, 2],
            "obstacles": [[1, 0], [1, 1], [1, 2]], "max_steps": 8})
        self.assertTrue(classify(task, "ANSWER: IMPOSSIBLE")["correct"])
        self.assertFalse(classify(task, 'ANSWER: ["S","S","E","E"]')["correct"])

    def test_certificate_mutants_fail_even_after_rehashing(self):
        examples = [fixture("math", {"tracks": [{"initial": 2, "steps": [["mul", 4]], "weight": 1}]}),
            fixture("logic", {"variables": 2, "clauses": [[1]]}),
            fixture("algorithms", {"nodes": 3, "edges": [[0, 2]]}),
            fixture("planning", {"width": 2, "height": 2, "start": [0, 0], "goal": [1, 1], "obstacles": [], "max_steps": 2})]
        for task in examples:
            bad = deepcopy(task)
            certificate = bad["reference_certificate"]
            if task["domain"] == "math": certificate["answer"] += 1
            elif task["domain"] == "logic": certificate["satisfying_assignments"] += 1
            elif task["domain"] == "algorithms": certificate["order"] = [1, 0, 2]
            else: certificate["distance_map_sha256"] = "0" * 64
            bad["reference_certificate_sha256"] = digest(certificate)
            bad["task_digest"] = digest({k: v for k, v in bad.items() if k != "task_digest"})
            with self.assertRaisesRegex(ValueError, "certificate check"):
                check_task(bad)

    def test_read_only_label_agreement_and_censored_diagnostics(self):
        task = fixture("logic", {"variables": 1, "clauses": [[1]]})
        base = {"task_id": task["task_id"], "root_id": task["root_id"], "status": "completed",
                "finish_reason": "stop", "gradable": True, "answer": "ANSWER: UNSAT",
                "correct": False, "raw_answer_grading": {"verdict": "incorrect"}}
        records = [{**base, "trace_id": "wrong"}, {**base, "trace_id": "censored", "status": "truncated",
                    "finish_reason": "length", "budget_censored": True, "correct": None, "gradable": False},
                   {**base, "trace_id": "unparseable", "correct": None, "gradable": False,
                    "answer": "SAT", "raw_answer_grading": {"verdict": "unparseable"}}]
        before = deepcopy(records)
        audit = audit_document(records, [task])
        self.assertEqual(records, before)
        self.assertTrue(audit["all_checked_recorded_labels_agree"])
        self.assertEqual(audit["recorded_primary_errors"], 1)
        self.assertEqual(audit["independent_diagnostic_counts"], {"incorrect": 2, "unparseable": 1})
        records[0]["correct"] = True
        self.assertEqual(audit_document(records, [task])["mismatch_trace_ids"], ["wrong"])


if __name__ == "__main__":
    unittest.main()
