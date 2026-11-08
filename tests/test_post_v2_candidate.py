"""Semantic reference checks and fail-closed offline design contracts."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from post_v2_design import tasks


class ExactReferenceTests(unittest.TestCase):
    def assertBoth(self, domain, data, expected):
        self.assertEqual(tasks.reference(domain, data)["answer"], expected)
        self.assertEqual(tasks.independent_answer(domain, data), expected)

    def test_modular_branch_uses_old_value_and_nonnegative_remainder(self):
        row = {"test_mod": 3, "threshold": 1, "then_mul": 2, "then_add": -20,
               "else_mul": 3, "else_add": 1}
        self.assertBoth("math", {"initial": 6, "modulus": 7, "steps": [row]}, 6)
        self.assertBoth("math", {"initial": 5, "modulus": 7, "steps": [row]}, 2)

    def test_cnf_counts_all_declared_variables_including_unused(self):
        self.assertBoth("logic", {"variables": 3, "clauses": [[1]]}, 4)
        self.assertBoth("logic", {"variables": 3, "clauses": []}, 8)
        self.assertBoth("logic", {"variables": 3, "clauses": [[1], [-1]]}, 0)
        self.assertBoth("logic", {"variables": 3, "clauses": [[1, -1]]}, 8)

    def test_negative_weight_dag_requires_true_shortest_cost(self):
        self.assertBoth("algorithms", {"nodes": 4, "start": 0, "goal": 3,
                        "edges": [[0, 1, 1], [0, 2, 2], [2, 1, -5], [1, 3, 0]]}, -3)
        self.assertBoth("algorithms", {"nodes": 3, "start": 0, "goal": 2, "edges": [[0, 1, -9]]}, "IMPOSSIBLE")

    def test_cycle_is_rejected_as_invalid_dag_construction(self):
        with self.assertRaisesRegex(ValueError, "DAG"):
            tasks.reference("algorithms", {"nodes": 2, "start": 0, "goal": 1,
                                           "edges": [[0, 1, -1], [1, 0, -1]]})

    def test_key_persists_and_door_is_checked_before_pickup(self):
        data = {"width": 4, "height": 1, "start": [0, 0], "goal": [3, 0], "obstacles": [],
                "keys": [{"cell": [1, 0], "key": 0}],
                "doors": [{"cell": [2, 0], "key": 0}, {"cell": [3, 0], "key": 0}]}
        self.assertBoth("planning", data, 3)
        data["doors"].append({"cell": [1, 0], "key": 0})
        self.assertBoth("planning", data, "IMPOSSIBLE")

    def test_grid_verifies_minimal_distance_with_required_detour(self):
        data = {"width": 3, "height": 3, "start": [0, 0], "goal": [2, 0], "obstacles": [[1, 1]],
                "keys": [{"cell": [0, 2], "key": 0}], "doors": [{"cell": [2, 0], "key": 0}]}
        self.assertBoth("planning", data, 6)
        self.assertLessEqual(tasks.reference("planning", data)["solver_work"]["reachable_states"], 18)


class CandidateConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = tasks.build()

    def test_fixed_roots_variants_and_deterministic_preview(self):
        self.assertEqual(self.corpus, tasks.build())
        rows = self.corpus["tasks"]
        roots = {row["root_id"] for row in rows}
        self.assertEqual((len(rows), len(roots)), (48, 24))
        for root in roots:
            pair = [row for row in rows if row["root_id"] == root]
            self.assertEqual({row["variant"] for row in pair}, {0, 1})
            self.assertEqual(pair[0]["reference"]["answer"], pair[1]["reference"]["answer"])
            self.assertEqual(tasks.structural_key(pair[0]["domain"], pair[0]["data"]),
                             tasks.structural_key(pair[1]["domain"], pair[1]["data"]))
            self.assertNotEqual(pair[0]["prompt"], pair[1]["prompt"])
        self.assertTrue(all(row["forced_split"] == "development" for row in rows))

    def test_all_reference_certificates_have_independent_agreement(self):
        self.assertTrue(all(tasks.verify_task(row) for row in self.corpus["tasks"]))
        for domain in tasks.DOMAINS:
            row = copy.deepcopy(next(row for row in self.corpus["tasks"] if row["domain"] == domain))
            row["reference"]["answer"] = -987654321
            row["reference_sha256"] = tasks.digest(row["reference"])
            self.assertFalse(tasks.verify_task(row))

    def test_generation_does_not_open_a_private_seed_or_model_results(self):
        from pathlib import Path
        with patch.object(Path, "read_bytes", side_effect=AssertionError("Unexpected filesystem input")):
            value = tasks.build()
        self.assertEqual(value["corpus_sha256"], self.corpus["corpus_sha256"])

    def test_distinct_development_seeds_cannot_reuse_task_or_root_identity(self):
        other = tasks.build(seed="explicitly-different-development-fixture")
        for field in ("root_id", "task_id"):
            self.assertTrue({r[field] for r in other["tasks"]}.isdisjoint({r[field] for r in self.corpus["tasks"]}))

    def test_no_reference_certificate_is_serialized_into_prompt(self):
        for row in self.corpus["tasks"]:
            self.assertNotIn(row["reference_sha256"], row["prompt"])
            self.assertNotIn("solver_work", row["prompt"])
            self.assertNotIn("instance_sha256", row["prompt"])

    def test_answer_grammar_is_fixed_before_any_model_results(self):
        row = self.corpus["tasks"][0]
        answer = row["reference"]["answer"]
        self.assertEqual(tasks.grade_answer(row, f"Explanation.\nANSWER: {answer}\n")["correct"], True)
        self.assertEqual(tasks.grade_answer(row, f"ANSWER: {answer + 1}")["correct"], False)
        for invalid in (None, "", str(answer), f"ANSWER: {answer}.0", "ANSWER: IMPOSSIBLE", "ANSWER: +01", "ANSWER: " + "9" * 1001):
            self.assertEqual(tasks.grade_answer(row, invalid), {"gradable": False, "parsed_answer": None, "correct": None})

    def test_answer_verifier_does_not_confuse_impossibility_with_format_failure(self):
        row = next(r for r in self.corpus["tasks"] if r["domain"] == "algorithms")
        self.assertEqual(tasks.grade_answer(row, "ANSWER: IMPOSSIBLE"), {"gradable": True, "parsed_answer": "IMPOSSIBLE", "correct": False})
        changed = copy.deepcopy(row)
        changed["reference"]["answer"] = 1234567
        with self.assertRaises(ValueError):
            tasks.grade_answer(changed, "ANSWER: 1234567")


class ProposedProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.build_post_v2_design import documents, PROTOCOL, OUTPUT
        cls.protocol_path, cls.output = PROTOCOL, OUTPUT
        cls.documents = documents()

    def test_execution_fails_closed_and_retains_original_budget_lineage(self):
        protocol = self.documents[self.protocol_path]
        self.assertFalse(protocol["execution"]["enabled"])
        self.assertIsNone(protocol["execution"]["paid_collector"])
        self.assertIsNone(protocol["execution"]["dispatch_deadline_utc"])
        self.assertEqual(protocol["execution"]["new_calls_in_this_work"], 0)
        self.assertEqual(protocol["parent"]["ledger_rows"], 984)
        self.assertEqual(protocol["budget_proposal"]["retained_charged_or_reserved_rub"], "823.5589067445220")
        self.assertEqual(protocol["budget_proposal"]["proposed_absolute_ceiling_rub"], "1423.5589067445220")
        self.assertIsNone(protocol["future_study"]["final_N"])

    def test_all_planned_rows_retain_balanced_root_pairs_and_no_outcomes(self):
        rows = self.documents[self.output / "proposed-roster.json"]
        self.assertEqual(len(rows), 192)
        self.assertEqual(len({row["cell_id"] for row in rows}), 192)
        for model in {row["model_id"] for row in rows}:
            for cap in (8192, 16384):
                group = [r for r in rows if r["model_id"] == model and r["output_budget_tokens"] == cap]
                self.assertEqual((len(group), len({r["root_id"] for r in group})), (48, 24))
                self.assertTrue(all("correct" not in row and "response" not in row for row in group))

    def test_prefix_and_support_thresholds_are_not_lowered(self):
        protocol = self.documents[self.protocol_path]
        self.assertEqual(protocol["measurement"]["primary_prefix_words"], 256)
        self.assertFalse(protocol["measurement"]["force_minimum_verbosity"])
        self.assertEqual(protocol["engineering_gate"]["minimum_primary_error_roots"], 3)
        self.assertEqual(protocol["engineering_gate"]["minimum_completed_gradeable_fraction"], .75)
        self.assertTrue(protocol["future_study"]["no_heldout_release"])

    def test_proposed_call_identity_is_bound_to_the_actual_corpus(self):
        corpus = self.documents[self.output / "development-preview.json"]
        for row in self.documents[self.output / "proposed-roster.json"]:
            self.assertEqual(row["cell_id"], tasks.digest([corpus["corpus_sha256"], row["task_id"], row["model_id"], row["output_budget_tokens"]]))

    def test_portable_design_metadata_survives_git_text_line_ending_conversion(self):
        from scripts.build_post_v2_design import ROOT, documents
        inventory = self.documents[self.output / "source-inventory.json"]
        audit = self.documents[self.output / "overlap-audit.json"]
        names = set(inventory["files_lf_sha256"])
        names.update(row["path"] for row in audit["legacy"]["sources"])
        names.add("artifacts/pilot-v2-recovery-2026-11-08/budget-final.json")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for name in names:
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = (ROOT / name).read_bytes()
                path.write_bytes(raw.replace(b"\r\n", b"\n") if path.suffix in (".py", ".json", ".md", ".jsonl") else raw)
            self.assertEqual(documents(project), self.documents)


if __name__ == "__main__":
    unittest.main()
