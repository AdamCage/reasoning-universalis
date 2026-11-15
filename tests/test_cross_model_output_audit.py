"""Synthetic diagnostics for strict content/schema/local-parser comparisons.

The audit must describe rejected content without repairing or salvaging labels.
No synthetic vote below is a research annotation or a reference label.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from scripts.audit_cross_model_outputs import classify


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "artifacts/machine-annotation-development-2026-11-08/codebook.json").read_bytes())["response_schema"]


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def item():
    return {"item_id": "synthetic-audit-item", "problem_statement": "Check the supplied result.",
            "current_segment": {"source_id": "synthetic-audit-item", "text": "Check α.\r\n𝛌 = 3. 👍"},
            "previous_segments": [{"source_id": "synthetic-audit-item:past:0", "text": "Earlier only."}]}


def vote():
    return {"item_id": "synthetic-audit-item", "primary_role": "verification", "secondary_roles": [],
            "confidence": "high", "reason_code": "check_existing",
            "evidence_quotes": [{"source_id": "synthetic-audit-item", "quote": "Check α."}]}


class CrossModelOutputAuditTests(unittest.TestCase):
    def assert_invalid_local(self, result, *, schema_valid):
        self.assertTrue(result["strict_json_valid"])
        self.assertIs(result["supplied_schema_valid"], schema_valid)
        self.assertFalse(result["local_parser_valid"])
        self.assertIsNone(result["local_vote"])
        self.assertEqual(result["schema_parser_mismatch"], schema_valid is True)
        self.assertTrue(result["failures"])
        self.assertTrue(all(isinstance(reason, str) and reason for reason in result["failures"]))

    def test_valid_vote_is_accepted_without_diagnostic_failures(self):
        original = vote()
        result = classify(encoded(original), item())
        self.assertTrue(result["strict_json_valid"])
        self.assertTrue(result["supplied_schema_valid"])
        self.assertTrue(result["local_parser_valid"])
        self.assertEqual(result["local_vote"], original)
        self.assertFalse(result["schema_parser_mismatch"])
        self.assertEqual(result["failures"], [])

    def test_primary_repeated_as_secondary_exposes_schema_parser_gap_without_salvage(self):
        content = vote()
        content["secondary_roles"] = ["verification"]
        result = classify(encoded(content), item())
        self.assert_invalid_local(result, schema_valid=True)
        self.assertIn("secondary_contains_primary", result["failures"])

    def test_duplicate_secondary_roles_fail_supplied_schema_and_local_parser(self):
        content = vote()
        content["secondary_roles"] = ["planning", "planning"]
        result = classify(encoded(content), item())
        self.assert_invalid_local(result, schema_valid=False)
        self.assertIn("secondary_duplicate", result["failures"])

    def test_context_quote_is_not_a_valid_current_segment_quote(self):
        content = vote()
        content["evidence_quotes"] = [{"source_id": "synthetic-audit-item", "quote": "Earlier only."}]
        result = classify(encoded(content), item())
        self.assert_invalid_local(result, schema_valid=True)
        self.assertIn("evidence_quote_context_only", result["failures"])

    def test_quote_source_must_match_current_anonymous_identity(self):
        content = vote()
        content["evidence_quotes"][0]["source_id"] = "synthetic-audit-item:past:0"
        result = classify(encoded(content), item())
        self.assert_invalid_local(result, schema_valid=True)
        self.assertIn("evidence_source_mismatch", result["failures"])

    def test_quote_requires_exact_unicode_and_newline_substring(self):
        content = vote()
        content["evidence_quotes"][0]["quote"] = "Check α.\n𝛌 = 3. 👍"
        result = classify(encoded(content), item())
        self.assert_invalid_local(result, schema_valid=True)
        self.assertIn("evidence_quote_not_current", result["failures"])
        content["evidence_quotes"][0]["quote"] = "Check α.\r\n𝛌 = 3. 👍"
        accepted = classify(encoded(content), item())
        self.assertTrue(accepted["local_parser_valid"])
        self.assertEqual(accepted["local_vote"], content)

    def test_quote_over_400_characters_fails_even_when_present_in_current_text(self):
        supplied = item()
        supplied["current_segment"]["text"] = "x" * 401
        content = vote()
        content["evidence_quotes"][0]["quote"] = "x" * 401
        result = classify(encoded(content), supplied)
        self.assert_invalid_local(result, schema_valid=False)
        self.assertIn("evidence_quote_too_long", result["failures"])

    def test_wrong_identity_is_not_repaired_to_match_input(self):
        content = vote()
        content["item_id"] = "another-valid-schema-string"
        result = classify(encoded(content), item())
        self.assert_invalid_local(result, schema_valid=True)
        self.assertIn("item_id_mismatch", result["failures"])

    def test_wrong_enums_extra_fields_and_missing_fields_are_rejected(self):
        changes = [{"primary_role": "invented_role"}, {"secondary_roles": ["ambiguous_other"]},
                   {"confidence": "certain"}, {"reason_code": "invented_reason"},
                   {"evidence_quotes": []}, {"confidence": True}, {"additional_field": "not permitted"}]
        for change in changes:
            with self.subTest(change=change):
                self.assert_invalid_local(classify(encoded({**vote(), **change}), item()), schema_valid=False)
        content = vote()
        del content["reason_code"]
        self.assert_invalid_local(classify(encoded(content), item()), schema_valid=False)

    def test_malformed_nested_types_are_classified_without_crashing_or_salvage(self):
        changes = [{"primary_role": []}, {"secondary_roles": None}, {"secondary_roles": ["planning", {}]},
                   {"confidence": {}}, {"reason_code": []}, {"evidence_quotes": {}}, {"evidence_quotes": [1]},
                   {"evidence_quotes": [{"source_id": [], "quote": "Check α."}]},
                   {"evidence_quotes": [{"source_id": "synthetic-audit-item", "quote": 12}]}]
        for change in changes:
            with self.subTest(change=change):
                self.assert_invalid_local(classify(encoded({**vote(), **change}), item()), schema_valid=False)

    def test_json_wrapping_duplicate_keys_and_nonfinite_numbers_are_not_repaired(self):
        valid = encoded(vote())
        malformed = ["```json\n" + valid + "\n```", "prefix " + valid, valid + " suffix", "",
                     '{"item_id":"synthetic-audit-item","item_id":"another"}',
                     '{"confidence":NaN}', '{"confidence":Infinity}',
                     '{"evidence_quotes":[{"quote":"a","quote":"b"}]}']
        for content in malformed:
            with self.subTest(content=content):
                result = classify(content, item())
                self.assertFalse(result["strict_json_valid"])
                self.assertIsNone(result["supplied_schema_valid"])
                self.assertFalse(result["local_parser_valid"])
                self.assertIsNone(result["local_vote"])
                self.assertFalse(result["schema_parser_mismatch"])
                self.assertTrue(result["failures"])

    def test_parseable_json_arrays_and_scalars_still_fail_annotation_schema(self):
        for content in ("[]", "null", "true", "12", '"a JSON string"'):
            with self.subTest(content=content):
                self.assert_invalid_local(classify(content, item()), schema_valid=False)

    def test_input_content_item_and_supplied_schema_are_not_mutated(self):
        supplied_item, supplied_schema = item(), copy.deepcopy(SCHEMA)
        content = encoded(vote())
        before_item, before_schema = copy.deepcopy(supplied_item), copy.deepcopy(supplied_schema)
        result = classify(content, supplied_item, schema=supplied_schema)
        self.assertTrue(result["local_parser_valid"])
        self.assertEqual(supplied_item, before_item)
        self.assertEqual(supplied_schema, before_schema)
        self.assertEqual(content, encoded(vote()))
        rejected = vote()
        rejected["secondary_roles"] = ["verification"]
        classify(encoded(rejected), supplied_item, schema=supplied_schema)
        self.assertEqual(supplied_item, before_item)
        self.assertEqual(supplied_schema, before_schema)


if __name__ == "__main__":
    unittest.main()
