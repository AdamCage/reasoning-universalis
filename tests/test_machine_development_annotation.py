"""Synthetic parser/panel tests and offline quote checks, never machine gold."""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import unittest

from machine_development.annotation import (
    MODEL, ROLES, SEEDS, agreement_summary, audit_item_ids, canonical, panel_result,
    parse_response, render_item, request_body, resolve_primary, select_balanced, summarize,
)
from scripts.prepare_machine_development import candidate_cost, snapshot_codebook


def item(identity="anonymous"):
    return {"item_id": identity, "problem_statement": "Solve the supplied problem; no reference answer.",
            "current_segment": {"source_id": identity, "text": "Check α.\r\nANSWER: reconsider the result."},
            "previous_segments": [{"source_id": identity + ":past", "text": "Earlier only."}]}


def vote(identity="anonymous", role="verification"):
    return {"item_id": identity, "primary_role": role, "secondary_roles": [], "confidence": "high",
            "reason_code": "check_existing", "evidence_quotes": [{"source_id": identity, "quote": "Check α."}]}


def pool():
    items, mapping = [], {}
    for root in range(24):
        for segment in range(9 if root < 8 else 8):
            identity = f"root{root}-segment{segment}"
            items.append(item(identity))
            mapping[identity] = {"root_id": f"root{root}", "source_model": "fixture-source", "domain": "fixture", "tier": "fixture"}
    return items, mapping


class MachineAnnotationTests(unittest.TestCase):
    def test_renderer_has_exact_data_keys_unchanged_CRLF_and_no_metadata(self):
        value = item()
        rendered = render_item(value, snapshot_codebook())
        payload = json.loads(rendered["messages"][1]["content"])
        self.assertEqual(set(payload), {"item_id", "problem_statement", "current_segment", "previous_segments", "ontology_definitions", "response_schema"})
        self.assertEqual(payload["current_segment"], value["current_segment"])
        self.assertIn("\r\nANSWER:", payload["current_segment"]["text"])
        self.assertFalse(rendered["oversized"])
        self.assertTrue(render_item(value, snapshot_codebook(), max_input_bytes=1)["oversized"])
        value["correctness"] = True
        with self.assertRaisesRegex(ValueError, "forbidden metadata"):
            render_item(value, snapshot_codebook())

    def test_future_or_overlong_context_and_forbidden_current_keys_refused(self):
        value = item()
        value["previous_segments"] *= 3
        with self.assertRaises(ValueError):
            render_item(value, snapshot_codebook())
        value = item()
        value["previous_segments"][0]["text"] = "x" * 1001
        with self.assertRaises(ValueError):
            render_item(value, snapshot_codebook())
        value = item()
        value["current_segment"]["provider"] = "hidden"
        with self.assertRaises(ValueError):
            render_item(value, snapshot_codebook())

    def test_strict_vote_never_repairs_json_or_borrows_context_quotes(self):
        self.assertEqual(parse_response(canonical(vote()), item())["primary_role"], "verification")
        invalid = [b'{"item_id":"anonymous","item_id":"other"}', b'{"x":NaN}', b'```json\n{}\n```', b'[]']
        for content in invalid:
            with self.assertRaises(ValueError):
                parse_response(content, item())
        value = vote()
        value["evidence_quotes"][0]["quote"] = "Earlier only."
        with self.assertRaises(ValueError):
            parse_response(canonical(value), item())

    def test_technical_missing_blocks_round2_and_second_round_is_not_pooled(self):
        incomplete = [vote()] * 4 + [None]
        self.assertEqual(panel_result(incomplete, 1)["status"], "technical_unresolved")
        with self.assertRaisesRegex(ValueError, "cannot open"):
            resolve_primary(incomplete, [vote()] * 5)
        first = [vote(role=role) for role in ("planning", "planning", "verification", "verification", "exploration")]
        second = [vote(role=role) for role in ("conclusion", "conclusion", "conclusion", "planning", "verification")]
        result = resolve_primary(first, second)
        self.assertEqual((result["role"], result["round_used"]), ("conclusion", 2))
        self.assertFalse(result["pooled_rounds"])
        self.assertEqual(panel_result([vote(role="ambiguous_other")] * 5, 1)["status"], "resolved_ambiguous")

    def test_fixed_seeds_route_and_disabled_reasoning_are_exact(self):
        for round_number in (1, 2):
            for index in range(5):
                body = request_body(item(), snapshot_codebook(), round_number, index)
                self.assertEqual(body["seed"], SEEDS[round_number - 1][index])
                self.assertEqual(body["model"], MODEL)
                self.assertEqual(body["provider"], {"order": ["BytePlus"], "allow_fallbacks": False})
                self.assertEqual((body["max_tokens"], body["temperature"], body["top_p"]), (1024, .7, 1.0))
                self.assertEqual(body["reasoning"], {"enabled": False})
        with self.assertRaises(ValueError):
            request_body(item(), snapshot_codebook(), True, 0)

    def test_balanced_subsets_full_pool_and_fixed_audit_are_order_independent(self):
        items, mapping = pool()
        chosen = select_balanced(items, mapping, 72)
        self.assertEqual(Counter(Counter(mapping[value["item_id"]]["root_id"] for value in chosen).values()), {3: 24})
        self.assertEqual(chosen, select_balanced(list(reversed(items)), mapping, 72))
        self.assertEqual(len(audit_item_ids(chosen)), 8)
        self.assertEqual(audit_item_ids(chosen), audit_item_ids(list(reversed(chosen))))
        complete = select_balanced(items, mapping, 200)
        self.assertEqual(len(complete), 200)
        self.assertEqual(len(audit_item_ids(complete)), 20)
        self.assertEqual(Counter(Counter(mapping[value["item_id"]]["root_id"] for value in complete).values()), {8: 16, 9: 8})

    def test_worst_quote_includes_all_both_rounds_and_fixed_audit(self):
        items, mapping = pool()
        result = candidate_cost(items, mapping, snapshot_codebook(), 72, (Decimal(".00001"), Decimal(".00002")))
        self.assertEqual(result["maximum_calls"], 760)
        self.assertEqual(Decimal(result["worst_case_reservation_rub"]), Decimal(result["round1_reservation_rub"]) +
                         Decimal(result["maximum_round2_reservation_rub"]) + Decimal(result["audit_reservation_rub"]))

    def test_constant_machine_agreement_is_not_defined_kappa_or_human_accuracy(self):
        values = [[vote()] * 5, [vote()] * 5]
        result = agreement_summary(values, roots=["r0", "r1"], bootstrap_replicates=10)
        self.assertEqual(result["raw_pairwise_agreement"], 1)
        self.assertIsNone(result["fleiss_kappa"])
        self.assertTrue(all(row["cohen_kappa"] is None for row in result["pairwise_cohen"]))
        self.assertIsNone(result["root_bootstrap"]["metrics"]["fleiss_kappa"]["interval95"])


if __name__ == "__main__":
    unittest.main()
