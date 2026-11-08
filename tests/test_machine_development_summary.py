"""Synthetic raw journals only: strict denominator, audit and budget replay."""
import copy
import json
from pathlib import Path
import sys
import unittest

from machine_development import annotation as ann
from scripts.summarize_machine_development import audit_summary, build, ledger_totals, verify_scope
from stage0.runner import encode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_machine_development_runner as fixtures


class SummaryHelpersTests(unittest.TestCase):
    def test_unknown_obligations_are_retained_separately_from_billing(self):
        rows = [{"id": "pending", "reservation_rub": "10", "charged_or_reserved_rub": "10", "reported_cost_rub": None, "state": "unknown"},
                {"id": "reported", "reservation_rub": "10", "charged_or_reserved_rub": "12", "reported_cost_rub": "12", "state": "finished"}]
        result = ledger_totals(rows)
        self.assertEqual(result["charged_or_reserved_rub"], "22")
        self.assertEqual(result["reported_cost_rub"], "12")
        self.assertEqual(result["commitments_without_reported_cost_rub"], "10")
        rows[0]["charged_or_reserved_rub"] = "9"
        with self.assertRaisesRegex(ValueError, "reservation was reduced"):
            ledger_totals(rows)

    def test_audit_disagreement_is_separate_and_does_not_repair_primary(self):
        original = {"primary_role": "planning"}
        repeated = {"primary_role": "verification"}
        result = {"audits": {"item": {"votes": [{"vote": repeated}] * 5}}}
        votes = {"item": {1: [original] * 5}}
        before = ann.canonical(votes)
        summary = audit_summary(result, votes)
        self.assertEqual(summary["planned_audit_votes"], 5)
        self.assertEqual(summary["comparable_consensus_items"], 1)
        self.assertEqual(summary["same_consensus_items"], 0)
        self.assertFalse(summary["primary_consensus_updated"])
        self.assertEqual(before, ann.canonical(votes))


class MachineSummaryReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixtures.MachineDevelopmentRunnerTests()
        cls.fixture.setUp()
        cls.runner = cls.fixture.runner()
        cls.result = cls.runner.run()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()

    def arguments(self):
        fixture, runner = self.fixture, self.runner
        return (runner.scope, fixture.protocol_path, fixture.input_dir / "items.json", fixture.input_dir / "codebook.json",
                fixture.input_dir / "mapping.json", runner.ledger_path)

    def test_complete_raw_replay_retains_conditional_slots_and_constant_kappa(self):
        out, report = self.fixture.project / "summary-output", self.fixture.project / "summary-report.md"
        ledger_before = self.runner.ledger_path.read_bytes()
        summary = build(*self.arguments(), out, report, source_root=self.fixture.project, calls=self.runner.calls)
        self.assertEqual(summary["planned_items"], 24)
        self.assertEqual(summary["call_coverage"]["all_planned_slots"], 255)
        self.assertEqual(summary["call_coverage"]["by_phase"]["round1"], {"valid": 120})
        self.assertEqual(summary["call_coverage"]["by_phase"]["round2"], {"not_scheduled_by_fixed_condition": 120})
        self.assertEqual(summary["call_coverage"]["by_phase"]["audit"], {"valid": 15})
        self.assertIsNone(summary["round1_agreement"]["fleiss_kappa"])
        self.assertEqual(summary["primary_status_counts"], {"resolved": 24})
        self.assertEqual(summary["source_descriptives"]["strata"]["source_model:unknown"]["role:planning"], 24)
        self.assertEqual(summary["source_descriptives"]["strata"]["source_model:unknown"]["role:conclusion"], 0)
        self.assertFalse(summary["accuracy_estimated"])
        self.assertEqual(summary["E0"], "not_passed")
        self.assertEqual(self.runner.ledger_path.read_bytes(), ledger_before)
        second_out, second_report = self.fixture.project / "summary-output-again", self.fixture.project / "summary-report-again.md"
        repeated = build(*self.arguments(), second_out, second_report, source_root=self.fixture.project, calls=self.runner.calls)
        self.assertEqual(summary, repeated)
        self.assertEqual({path.name: path.read_bytes() for path in out.iterdir()}, {path.name: path.read_bytes() for path in second_out.iterdir()})
        self.assertEqual(report.read_bytes(), second_report.read_bytes())

    def test_changed_consensus_or_dropped_conditional_registry_cannot_pass(self):
        path = self.runner.scope / "results.json"
        original = path.read_bytes()
        value = json.loads(original)
        value["items"][0]["primary"]["role"] = "verification"
        try:
            path.write_bytes(encode(value))
            with self.assertRaisesRegex(ValueError, "primary consensus"):
                verify_scope(*self.arguments(), source_root=self.fixture.project, calls=self.runner.calls)
            value = json.loads(original)
            value["all_planned_calls"].pop()
            path.write_bytes(encode(value))
            with self.assertRaisesRegex(ValueError, "planned order"):
                verify_scope(*self.arguments(), source_root=self.fixture.project, calls=self.runner.calls)
        finally:
            path.write_bytes(original)

    def test_changed_earlier_ledger_obligation_is_not_silently_rebased(self):
        path = self.runner.ledger_path
        original = path.read_bytes()
        value = json.loads(original)
        value[0]["charged_or_reserved_rub"] = "0"
        try:
            path.write_bytes(encode(value))
            with self.assertRaisesRegex(ValueError, "Earlier shared-ledger"):
                verify_scope(*self.arguments(), source_root=self.fixture.project, calls=self.runner.calls)
        finally:
            path.write_bytes(original)

    def test_unknown_first_votes_keep_all_registry_and_block_audit_repair(self):
        fixture = fixtures.MachineDevelopmentRunnerTests()
        fixture.setUp()
        try:
            runner = fixture.runner()
            fixture.transport.mode = "unknown"
            runner.run()
            summary = build(runner.scope, fixture.protocol_path, fixture.input_dir / "items.json", fixture.input_dir / "codebook.json",
                fixture.input_dir / "mapping.json", runner.ledger_path, fixture.project / "unknown-summary", fixture.project / "unknown.md",
                source_root=fixture.project, calls=runner.calls)
            self.assertEqual(summary["primary_status_counts"], {"technical_unresolved": 24})
            self.assertEqual(summary["call_coverage"]["all_planned_slots"], 255)
            self.assertGreater(summary["call_coverage"]["transport_unknown_slots"], 0)
            self.assertEqual(summary["audit"]["planned_audit_votes"], 15)
            self.assertEqual(summary["audit"]["comparable_consensus_items"], 0)
            self.assertFalse(summary["audit"]["primary_consensus_updated"])
        finally:
            fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
