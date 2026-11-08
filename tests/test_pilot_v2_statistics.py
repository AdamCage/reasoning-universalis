"""Offline scientific guards for the prospective v2 support design."""
import copy
import math
import unittest

from pilot_v2.statistical_design import (
    binomial_tail, binomial_failure_probability, fold_support, pool_root_support,
    required_roots_for_support, required_n_tables, simulate_paired_loss_precision,
    simulate_support, summarize_support, validate_probe_layout, wilson_interval,
)


def fixture():
    tasks, records = [], []
    for root in range(6):
        for variant in range(2):
            task = {"task_id": f"r{root}:v{variant}", "root_id": f"r{root}",
                    "domain": "logic", "tier": "hard"}
            tasks.append(task)
            for model in ("a", "b"):
                for cap in (2048, 8192):
                    records.append({**task, "trace_id": f"{task['task_id']}:{model}:{cap}",
                        "model": model, "output_budget_tokens": cap, "status": "completed",
                        "finish_reason": "stop", "gradable": True, "correct": not (root < 3 and variant == 0),
                        "text": "reason " * 512, "identity_verified": True, "provider_route_verified": True,
                        "observed_trace_status": "visible_trace_candidate"})
    return tasks, records


def primary(result, model="a", cap=2048):
    return next(row for row in result["groups"] if row["model"] == model and
                row["output_budget_tokens"] == cap and row["prefix_budget_words"] == 256)


class SupportTests(unittest.TestCase):
    def test_paired_variants_and_source_models_are_not_independent_roots(self):
        tasks, records = fixture()
        result = summarize_support(records, tasks, ["a", "b"])
        group = primary(result)
        self.assertEqual((group["planned_attempts"], group["error_traces"], group["error_roots"],
                          group["correct_roots"], group["mixed_roots"]), (12, 3, 3, 6, 3))
        pooled = pool_root_support([group, primary(result, "b")])
        self.assertEqual(len(pooled["error_root_ids"]), 3)
        self.assertEqual(len(pooled["planned_root_ids"]), 6)
        self.assertEqual(result["selected_common_output_cap"], 2048)

    def test_unsent_cells_keep_the_planned_denominator_and_block_cap_selection(self):
        tasks, records = fixture()
        records = [row for row in records if not (row["model"] == "a" and row["output_budget_tokens"] == 2048
                                                   and row["task_id"] in {"r4:v0", "r4:v1", "r5:v0", "r5:v1"})]
        result = summarize_support(records, tasks, ["a", "b"])
        group = primary(result)
        self.assertEqual(group["planned_attempts"], 12)
        self.assertEqual(group["recorded_attempts"], 8)
        self.assertAlmostEqual(group["completed_gradeable_fraction_of_planned"], 8 / 12)
        self.assertIsNone(group["error_root_yield_wilson95"])
        self.assertIsNone(result["selected_common_output_cap"])

    def test_first_answer_marker_censors_prefix_before_counting(self):
        tasks, records = fixture()
        for record in records:
            if not record["correct"]:
                record["text"] = "reason " * 128 + "ANSWER: 0 " + "future " * 1024
        result = summarize_support(records, tasks, ["a", "b"])
        self.assertEqual(primary(result)["error_roots"], 0)
        short = next(group for group in result["groups"] if group["model"] == "a" and
                     group["output_budget_tokens"] == 2048 and group["prefix_budget_words"] == 128)
        self.assertEqual(short["error_roots"], 3)
        self.assertIsNone(result["selected_common_output_cap"])

    def test_censored_diagnostic_labels_never_enter_main_support(self):
        tasks, records = fixture()
        for record in records:
            if not record["correct"]:
                record.update(status="truncated", finish_reason="length", budget_censored=True,
                              correct=None, gradable=False, raw_answer_grading={"verdict": "incorrect"})
        result = summarize_support(records, tasks, ["a", "b"])
        group = primary(result)
        self.assertEqual(group["error_roots"], 0)
        self.assertEqual(group["censored_diagnostic_error_roots"], 3)
        self.assertEqual(group["censored_diagnostic_prefix_eligible"], 3)
        self.assertFalse(result["allow_budget_censored_gradeable"])
        self.assertIsNone(result["selected_common_output_cap"])
        records[0]["correct"] = False
        with self.assertRaisesRegex(ValueError, "must remain null"):
            summarize_support(records, tasks, ["a", "b"])

    def test_duplicate_attempts_and_conflicting_output_conditions_fail_closed(self):
        tasks, records = fixture()
        with self.assertRaisesRegex(ValueError, "Repeated attempt"):
            summarize_support(records + records[:1], tasks, ["a", "b"])
        records[0]["max_output_tokens"] = 8192
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            summarize_support(records, tasks, ["a", "b"])

    def test_primary_requires_explicit_route_and_visible_channel_acceptance(self):
        tasks, records = fixture()
        for record in records:
            if not record["correct"]:
                record["identity_verified"] = False
        result = summarize_support(records, tasks, ["a", "b"])
        group = primary(result)
        self.assertEqual(group["error_roots"], 0)
        self.assertEqual(group["operational_validation_excluded"], 3)
        self.assertIsNone(result["selected_common_output_cap"])

    def test_unknown_blocks_even_when_observed_class_floor_is_met(self):
        tasks, records = fixture()
        records[-1].update(status="unknown", correct=None, finish_reason=None, http_status=None)
        result = summarize_support(records, tasks, ["a", "b"])
        self.assertTrue(primary(result)["engineering_readiness"])
        self.assertFalse(result["entire_fixed_roster_resolved"])
        self.assertIsNone(result["selected_common_output_cap"])

    def test_planned_placeholders_never_count_as_resolved_attempts(self):
        for status in ("not_dispatched", "unresolved_attempt", "unresolved_intent"):
            with self.subTest(status=status):
                tasks, records = fixture()
                records[-1].update(status=status, correct=None, gradable=False, text="", finish_reason=None)
                result = summarize_support(records, tasks, ["a", "b"])
                self.assertFalse(result["entire_fixed_roster_resolved"])
                self.assertIsNone(result["selected_common_output_cap"])
                row = primary(result, "b", 8192)
                if status == "not_dispatched":
                    self.assertEqual(row["not_dispatched"], 1)
                    self.assertEqual(row["recorded_attempts"], 11)
                    self.assertEqual(row["unknown_attempts"], 0)
                else:
                    self.assertGreater(row["unknown_attempts"], 0)

    def test_probe_layout_is_fixed_without_creating_future_splits(self):
        tasks = [{"task_id": f"{domain}:{tier}:{root}:{variant}", "root_id": f"{domain}:{tier}:{root}",
                  "domain": domain, "tier": tier} for domain in ("math", "logic", "algorithms", "planning")
                 for tier in ("a", "b", "c") for root in range(2) for variant in range(2)]
        self.assertEqual(validate_probe_layout(tasks)["maximum_generation_calls"], 192)
        with self.assertRaises(ValueError):
            validate_probe_layout(tasks[:-1])

    def test_future_role_floors_and_leakage_guard(self):
        def groups(prefix, n):
            roots = [f"{prefix}:{i}" for i in range(n)]
            return [{"output_budget_tokens": 8192, "prefix_budget_words": 256,
                     **{field: roots for field in ("planned_root_ids", "eligible_root_ids", "error_root_ids",
                                                  "correct_root_ids", "mixed_root_ids")}}]
        train, val, target = groups("train", 10), groups("val", 5), groups("target", 20)
        result = fold_support(train, val, target)
        self.assertTrue(result["class_floor_ready"])
        self.assertEqual(result["roles"]["target"]["eligible_roots"], 20)  # mixed roots, not forty
        with self.assertRaisesRegex(ValueError, "crosses"):
            fold_support(train, val, copy.deepcopy(train))


class PlanningTests(unittest.TestCase):
    def test_wilson_boundary_and_zero_sample_are_not_false_zero_precision(self):
        self.assertIsNone(wilson_interval(0, 0))
        lower, upper = wilson_interval(0, 24)
        self.assertAlmostEqual(lower, 0.)
        self.assertGreater(upper, .1)
        self.assertLess(upper, .2)
        with self.assertRaises(ValueError):
            wilson_interval(25, 24)

    def test_binomial_root_tail_matches_hand_calculation(self):
        self.assertAlmostEqual(binomial_tail(4, .5, 3), 5 / 16)
        self.assertEqual(binomial_tail(24, 0, 3), 0.)
        self.assertEqual(binomial_tail(24, 1, 3), 1.)
        self.assertEqual(binomial_tail(2, .5, 3), 0.)
        self.assertAlmostEqual(binomial_failure_probability(4, .5, 3), 11 / 16)

    def test_conditional_required_N_boundary_and_infeasibility(self):
        certain = required_roots_for_support(1., 1., 3, 3, maximum_roots=100)
        self.assertEqual(certain["required_roots"], 3)
        impossible = required_roots_for_support(0., 1., 3, 3, maximum_roots=100)
        self.assertIsNone(impossible["required_roots"])
        known = required_roots_for_support(1., .5, 1, 1, maximum_roots=100)
        self.assertEqual(known["required_roots"], 4)  # 1-(1/2)^4 >= .9; N=3 fails
        self.assertGreaterEqual(known["joint_support_lower_bound"], .90)
        self.assertLess(known["previous_N_joint_lower_bound"], .90)
        scenarios = {"fixture": {"none": 0., "error_only": 0., "correct_only": 0., "mixed": 1.}}
        table = required_n_tables(scenarios)
        self.assertEqual([row["required_roots"] for row in table["support"]], [3, 10, 5, 20])
        first = table["precision"][0]
        self.assertEqual(first["required_roots"], math.ceil((1.96 * .05 / .005) ** 2))

    def test_joint_support_preserves_mixed_root_dependence(self):
        probabilities = {"none": .5, "error_only": 0., "correct_only": 0., "mixed": .5}
        result = simulate_support(4, probabilities, 3, repetitions=5000, seed=7)
        self.assertAlmostEqual(result["exact_binomial_error_support"], 5 / 16)
        # Errors and correct support coincide here; multiplying marginals would
        # incorrectly give (5/16)^2 instead of 5/16.
        self.assertLess(abs(result["fraction_joint_support"] - 5 / 16), .025)
        self.assertGreater(abs(result["fraction_joint_support"] - (5 / 16) ** 2), .15)
        self.assertEqual(result, simulate_support(4, probabilities, 3, 5000, 7))

    def test_null_and_rare_event_precision_are_scenarios_not_empirical_power(self):
        null = simulate_paired_loss_precision(96, 0., .05, 4000, 9)
        self.assertLess(null["fraction_interval_excluding_zero"], .08)
        self.assertGreater(null["fraction_covering_assumed_effect"], .92)
        rare = simulate_paired_loss_precision(24, 0., .05, 4000, 9, "rare_event", .02)
        self.assertGreater(rare["fraction_zero_width_intervals"], .5)
        self.assertIn("not_validated_power", rare["kind"])
        self.assertTrue(math.isfinite(rare["mean_interval_width"]))


if __name__ == "__main__":
    unittest.main()
