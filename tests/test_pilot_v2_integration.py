"""Actual synthetic runner outputs cross the offline class-support boundary."""
import json
import unittest

from pilot_v2.statistical_design import summarize_support
from stage0.runner import encode
from tests import test_pilot_v2_runner as runner_fixtures


def paired_fixture_grade(task, text):
    """Three mixed original roots; this is a synthetic integration label only."""
    root = int(task["root_id"].split("-")[-1])
    variant = int(task["task_id"].split("-")[-1])
    correct = not (root < 3 and variant == 0)
    return {"verdict": "correct" if correct else "incorrect", "correct": correct,
            "gradable": True, "verifier_id": "synthetic-integration-only"}


class PilotV2IntegrationTests(unittest.TestCase):
    def fixture(self):
        # Composition avoids inheriting/re-running the runner unit test suite.
        harness = runner_fixtures.PilotV2RunnerTests()
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        runner = harness.runner()
        runner.fixture_verifier = paired_fixture_grade
        tasks = json.loads(harness.tasks_path.read_bytes())["tasks"]
        return harness, runner, tasks

    def support(self, output, tasks):
        return summarize_support(output["records"], tasks, list(runner_fixtures.PROVIDERS))

    def assert_planned_denominators(self, result):
        self.assertEqual(result["planned_generation_attempts"], 192)
        self.assertTrue(all(group["planned_attempts"] == 48 for group in result["groups"]))
        self.assertTrue(all(group["planned_roots"] == 24 for group in result["groups"]))

    def test_actual_192_completed_outputs_pass_support_without_inflating_mixed_roots(self):
        harness, runner, tasks = self.fixture()
        output = runner.run()
        self.assertEqual(len(harness.transport.paid), 192)
        self.assertEqual(len(output["records"]), 192)
        self.assertTrue(all(record["status"] == "completed" for record in output["records"]))
        result = self.support(output, tasks)
        self.assert_planned_denominators(result)
        self.assertTrue(result["entire_fixed_roster_resolved"])
        self.assertEqual(result["selected_common_output_cap"], 2048)
        for group in result["groups"]:
            if group["prefix_budget_words"] != 256:
                continue
            self.assertEqual(group["completed_gradeable"], 48)
            self.assertEqual(group["error_roots"], 3)
            self.assertEqual(group["correct_roots"], 24)
            self.assertEqual(group["mixed_roots"], 3)
            self.assertEqual(len(group["eligible_root_ids"]), 24)
            self.assertTrue(group["engineering_readiness"])

    def test_deadline_with_zero_paid_calls_retains_all_192_unsent_cells(self):
        harness, runner, tasks = self.fixture()
        runner.settings.deadline = "2000-01-01T00:00:00+00:00"
        output = runner.run()
        self.assertEqual(harness.transport.paid, [])
        self.assertEqual(len(output["records"]), 192)
        self.assertTrue(all(record["status"] == "not_dispatched" for record in output["records"]))
        result = self.support(output, tasks)
        self.assert_planned_denominators(result)
        self.assertFalse(result["entire_fixed_roster_resolved"])
        self.assertIsNone(result["selected_common_output_cap"])
        self.assertTrue(all(group["completed_gradeable"] == 0 for group in result["groups"]))
        self.assertTrue(all(not group["engineering_readiness"] for group in result["groups"]))

    def test_one_actual_unresolved_intent_blocks_global_gate_despite_class_support(self):
        harness, runner, tasks = self.fixture()
        runner.preflight()
        cell = next(cell for cell in runner.plan["cells"] if cell["root_id"] == "root-23"
                    and cell["task_id"].endswith("-1") and cell["output_budget_tokens"] == 8192)
        intent = runner.scope / "intents" / (cell["call_id"] + ".json")
        intent.parent.mkdir(parents=True, exist_ok=True)
        intent.write_bytes(encode({"synthetic_unfinished_intent": True}))
        output = runner.run()
        self.assertEqual(len(harness.transport.paid), 191)
        self.assertEqual(len(output["records"]), 192)
        unresolved = [record for record in output["records"] if record["status"] != "completed"]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["status"], "unresolved_intent")
        self.assertEqual(unresolved[0]["request_state"], "unknown")
        result = self.support(output, tasks)
        self.assert_planned_denominators(result)
        self.assertFalse(result["entire_fixed_roster_resolved"])
        self.assertIsNone(result["selected_common_output_cap"])
        primary = [group for group in result["groups"] if group["prefix_budget_words"] == 256]
        self.assertTrue(all(group["completed_gradeable"] >= 36 for group in primary))
        self.assertTrue(all(group["error_roots"] >= 3 and group["correct_roots"] >= 3 for group in primary))
        affected = next(group for group in primary if group["model"] == cell["model"]
                        and group["output_budget_tokens"] == 8192)
        self.assertFalse(affected["allocation_complete_and_no_unknown"])
        self.assertGreaterEqual(affected["unknown_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
