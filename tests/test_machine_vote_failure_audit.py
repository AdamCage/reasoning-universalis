"""Small diagnostics regressions; the frozen semantic parser remains authoritative."""
import copy
import json
import unittest

from scripts.audit_machine_vote_failures import diagnose


class MachineFailureAuditTests(unittest.TestCase):
    def fixture(self):
        item = {"item_id": "fixture", "problem_statement": "Data only.",
                "current_segment": {"source_id": "fixture", "text": "x" * 445}, "previous_segments": []}
        vote = {"item_id": "fixture", "primary_role": "planning", "secondary_roles": [], "confidence": "high",
                "reason_code": "strategy", "evidence_quotes": [{"source_id": "fixture", "quote": "x"}]}
        response = {"http_status": 200, "json": {"model": "deepseek/deepseek-v4.1-flash", "provider": "BytePlus",
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(vote)}}]}}
        return item, vote, response

    def test_forbidden_field_and_exact_overlength_quote_have_distinct_causes(self):
        item, vote, response = self.fixture()
        self.assertEqual(diagnose(response, item)["technical_status"], "valid")
        vote["reason_code_note"] = "Extra prose cannot repair the schema."
        response["json"]["choices"][0]["message"]["content"] = json.dumps(vote)
        extra = diagnose(response, item)
        self.assertEqual(extra["category"], "forbidden_extra_field")
        self.assertEqual(extra["content_diagnostics"]["extra_fields"], ["reason_code_note"])
        del vote["reason_code_note"]
        vote["evidence_quotes"][0]["quote"] = "x" * 445
        response["json"]["choices"][0]["message"]["content"] = json.dumps(vote)
        long = diagnose(response, item)
        self.assertEqual(long["category"], "evidence_quote_length_outside_1_to_400")
        self.assertTrue(long["content_diagnostics"]["quotes"][0]["exact_substring_of_current_segment"])
        self.assertIn("Quote not present", long["exception_chain"][-1]["message"])

    def test_nonliteral_quote_is_not_misclassified_as_length_or_repaired(self):
        item, vote, response = self.fixture()
        vote["evidence_quotes"][0]["quote"] = "unseen"
        response["json"]["choices"][0]["message"]["content"] = json.dumps(vote)
        before = copy.deepcopy(response)
        result = diagnose(response, item)
        self.assertEqual(result["category"], "evidence_quote_not_exact_substring")
        self.assertEqual(response, before)
        self.assertIsNone(result["vote"])

    def test_route_completion_and_duplicate_json_fail_without_repair(self):
        item, vote, response = self.fixture()
        response["json"]["provider"] = "other"
        self.assertEqual(diagnose(response, item)["category"], "transport_or_identity_invalid")
        response["json"]["provider"] = "BytePlus"
        response["json"]["choices"][0]["finish_reason"] = "length"
        self.assertEqual(diagnose(response, item)["category"], "output_not_complete")
        response["json"]["choices"][0]["finish_reason"] = "stop"
        response["json"]["choices"][0]["message"]["content"] = '{"item_id":"fixture","item_id":"fixture"}'
        self.assertEqual(diagnose(response, item)["category"], "strict_json_invalid")


if __name__ == "__main__":
    unittest.main()
