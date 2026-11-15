"""Engineering integrity checks for the bounded cross-family pilot.

All synthetic votes below exercise software only. They are never scientific
annotations, human reference labels, or evidence about model agreement.
"""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from cross_model.annotation import parse_response, render, request_body, validate_envelope
from cross_model.analysis import bootstrap_draws, pair_metrics
from cross_model.prepare import prepare
from cross_model.runner import Collector, cells, quote
from cross_model.common import ARTIFACT, PROTOCOL, ROUTES, write


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "artifacts/machine-annotation-development-2026-11-08"
OUTPUT = ROOT / "artifacts/cross-model-2026-11-15"


def read(path):
    return json.loads(path.read_bytes())


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def item():
    return {"item_id": "synthetic-unicode", "problem_statement": "Check the supplied result.",
            "current_segment": {"source_id": "synthetic-unicode", "text": "Check α.\r\n𝛌 = 3. 👍"},
            "previous_segments": [{"source_id": "synthetic-unicode:past:0", "text": "Earlier only."}]}


def vote():
    return {"item_id": "synthetic-unicode", "primary_role": "verification", "secondary_roles": [],
            "confidence": "high", "reason_code": "check_existing",
            "evidence_quotes": [{"source_id": "synthetic-unicode", "quote": "Check α.\r\n𝛌 = 3. 👍"}]}


def rendered_payload(value):
    result = render(value, read(PARENT / "codebook.json"))
    messages = result["messages"] if isinstance(result, dict) else result
    return json.loads(messages[1]["content"])


class CrossModelIntegrityTests(unittest.TestCase):
    def test_parent_frozen_inputs_and_results_match_sealed_evidence(self):
        manifest = read(ROOT / "evidence/machine-annotation-development-2026-11-08/manifest.json")
        expected = {row["path"][len("project/"):]: row["sha256"]
                    for row in manifest["payload"]["files"] if row["path"].startswith("project/")}
        for name in ("input-items.json", "machine-mapping.json", "codebook.json", "results.json",
                     "summary.json", "source-inventory.json"):
            path = PARENT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             expected[path.relative_to(ROOT).as_posix()], name)
        source_files = read(PARENT / "source-inventory.json")["files"]
        with zipfile.ZipFile(PARENT / "source-snapshot.zip") as archive:
            self.assertEqual(set(archive.namelist()), {"source/" + name for name in source_files} | {"source-inventory.json"})
            self.assertEqual(archive.read("source-inventory.json"), (PARENT / "source-inventory.json").read_bytes())
            for name, expected_sha in source_files.items():
                self.assertEqual(hashlib.sha256(archive.read("source/" + name)).hexdigest(), expected_sha)

    def test_preparation_is_deterministic_preserves_offsets_and_never_changes_parent(self):
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in PARENT.iterdir() if path.is_file()}
        with tempfile.TemporaryDirectory(prefix="cross-model-integrity-") as temporary:
            first = prepare(ROOT, output_dir=Path(temporary) / "a")
            second = prepare(ROOT, output_dir=Path(temporary) / "b")
            self.assertEqual(first["items"], second["items"])
            self.assertEqual(first["mapping"], second["mapping"])
            self.assertEqual(len(first["items"]), 72)
            ids = [value["item_id"] for value in first["items"]]
            self.assertEqual(len(set(ids)), 72)
            self.assertEqual(len(first["core_ids"]), 48)
            self.assertEqual(len(first["challenge_ids"]), 24)
            self.assertFalse(set(first["core_ids"]) & set(first["challenge_ids"]))
            self.assertEqual(Counter(Counter(row["root_id"] for row in first["mapping"].values()).values()), {3: 24})
            self.assertEqual(len(first["ablation_ids"]), 24)
            self.assertTrue(set(first["ablation_ids"]) <= set(first["core_ids"]))
            self.assertEqual(len({first["mapping"][i]["root_id"] for i in first["ablation_ids"]}), 24)
            original_items = {value["item_id"]: value for value in read(PARENT / "input-items.json")["items"]}
            original_mapping = read(PARENT / "machine-mapping.json")["items"]
            traces = {value["item_id"]: value["text"] for value in
                      read(ROOT / "artifacts/e0-human-development-2026-11-08/public-boundary/A/items.json")["items"]}
            for selected in first["items"]:
                identity = selected["item_id"]
                self.assertEqual(selected, original_items[identity])
                mapping = first["mapping"][identity]
                for key, value in original_mapping[identity].items():
                    self.assertEqual(mapping[key], value)
                text = traces[mapping["trace_item_id"]]
                start, end = mapping["char_start"], mapping["char_end"]
                self.assertEqual(text[start:end], selected["current_segment"]["text"])
                self.assertEqual(end - start, len(selected["current_segment"]["text"]))
                previous = "".join(value["text"] for value in selected["previous_segments"])
                self.assertTrue(text[:start].endswith(previous))
            for field in ("domain", "source_model"):
                self.assertEqual({row[field] for row in first["mapping"].values()},
                                 {row[field] for row in original_mapping.values()})
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in PARENT.iterdir() if path.is_file()})

    def test_prompt_values_are_exact_and_metadata_has_no_entry_point(self):
        value = item()
        payload = rendered_payload(value)
        self.assertEqual(set(payload), {"item_id", "problem_statement", "current_segment", "previous_segments",
                                        "ontology_definitions", "response_schema"})
        self.assertEqual(payload["current_segment"], value["current_segment"])
        self.assertEqual(payload["problem_statement"], value["problem_statement"])
        self.assertEqual(payload["previous_segments"], ["Earlier only."])
        self.assertIn("\r\n𝛌", payload["current_segment"]["text"])
        for forbidden in ("reference_role", "old_machine_label", "correctness", "future_segments", "source_model"):
            dirty = copy.deepcopy(value)
            dirty[forbidden] = "NEVER_SEND_THIS_METADATA"
            with self.subTest(forbidden=forbidden), self.assertRaises(ValueError):
                rendered_payload(dirty)
        for location in ("current_segment", "previous_segments"):
            dirty = copy.deepcopy(value)
            nested = dirty[location] if location == "current_segment" else dirty[location][0]
            nested["future_segment"] = "NEVER_SEND_THIS_METADATA"
            with self.subTest(location=location), self.assertRaises(ValueError):
                rendered_payload(dirty)

    def test_strict_parser_rejects_repair_candidates_and_noncurrent_evidence(self):
        self.assertEqual(parse_response(canonical(vote()), item())["primary_role"], "verification")
        invalid = ['{"item_id":"synthetic-unicode","item_id":"another"}', '{"value":NaN}',
                   '```json\n{}\n```', '[]', 'null', '{} trailing']
        for content in invalid:
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_response(content, item())
        for change in (
            {"item_id": "different-item"}, {"primary_role": "invented_role"},
            {"secondary_roles": ["verification"]}, {"secondary_roles": ["planning", "planning"]},
            {"confidence": "certain"}, {"reason_code": "made_up_reason"}, {"evidence_quotes": []},
            {"extra": "forbidden"},
            {"evidence_quotes": [{"source_id": "synthetic-unicode", "quote": "Earlier only."}]},
            {"evidence_quotes": [{"source_id": "synthetic-unicode:past:0", "quote": "Earlier only."}]},
            {"evidence_quotes": [{"source_id": "synthetic-unicode", "quote": "Check α.\n𝛌 = 3. 👍"}]},
        ):
            dirty = {**vote(), **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_response(canonical(dirty), item())

    def test_context_ablation_changes_only_past_context_and_never_mutates_source(self):
        original = item()
        before = copy.deepcopy(original)
        codebook = read(PARENT / "codebook.json")
        full = request_body(original, codebook, "fixture-model", "fixture-provider")
        ablated = request_body(original, codebook, "fixture-model", "fixture-provider", condition="without_context")
        self.assertEqual(original, before)
        full_payload = json.loads(full["messages"][1]["content"])
        ablated_payload = json.loads(ablated["messages"][1]["content"])
        self.assertEqual(ablated_payload["previous_segments"], [])
        self.assertEqual(full_payload["previous_segments"], ["Earlier only."])
        full_payload.pop("previous_segments")
        ablated_payload.pop("previous_segments")
        self.assertEqual(full_payload, ablated_payload)
        full.pop("messages")
        ablated.pop("messages")
        self.assertEqual(full, ablated)

    def test_invalid_transport_identity_or_completion_never_creates_label(self):
        payload = {"model": "fixture-model", "provider": "fixture-provider",
                   "choices": [{"finish_reason": "stop", "message": {"content": canonical(vote())}}]}
        response = {"http_status": 200, "json": payload}
        parsed = validate_envelope(response, item(), "fixture-model", "fixture-provider")
        self.assertEqual(parsed["technical_status"], "valid")
        self.assertEqual(parsed["vote"]["primary_role"], "verification")
        invalid = []
        for change in ({"http_status": 429}, {"network_error": "timeout"}):
            invalid.append({**copy.deepcopy(response), **change})
        for field, value in (("model", "wrong-model"), ("provider", "wrong-provider"), ("error", {"message": "failure"})):
            dirty = copy.deepcopy(response)
            dirty["json"][field] = value
            invalid.append(dirty)
        for finish in ("length", "error", None):
            dirty = copy.deepcopy(response)
            dirty["json"]["choices"][0]["finish_reason"] = finish
            invalid.append(dirty)
        dirty = copy.deepcopy(response)
        dirty["json"]["choices"][0]["message"]["content"] = "not JSON"
        invalid.append(dirty)
        for bad in invalid:
            with self.subTest(response=bad):
                parsed = validate_envelope(bad, item(), "fixture-model", "fixture-provider")
                self.assertNotEqual(parsed["technical_status"], "valid")
                self.assertIsNone(parsed["vote"])

    def test_bootstrap_resamples_whole_task_roots_with_replacement(self):
        rows = [{"item_id": f"{root}-{index}", "root_id": root,
                 "reference_role": "planning", "new_role": "planning"}
                for root, count in (("r0", 2), ("r1", 3), ("r2", 4)) for index in range(count)]
        draws = list(bootstrap_draws(rows, replicates=60, seed=7843))
        self.assertEqual(draws, list(bootstrap_draws(rows, replicates=60, seed=7843)))
        self.assertEqual(len(draws), 60)
        by_root = {root: [row for row in rows if row["root_id"] == root] for root in ("r0", "r1", "r2")}
        has_duplicate_root = False
        for sample in draws:
            counts = Counter(row["item_id"] for row in sample)
            multiplicities = []
            for group in by_root.values():
                within = {counts[row["item_id"]] for row in group}
                self.assertEqual(len(within), 1, "A task root was split across resampling units")
                multiplicities.append(within.pop())
            self.assertEqual(sum(multiplicities), len(by_root))
            has_duplicate_root |= max(multiplicities) > 1
        self.assertTrue(has_duplicate_root, "Cluster bootstrap must sample with replacement")

    def test_invalid_and_unresolved_cases_remain_in_denominators(self):
        labels = [("planning", "planning"), ("planning", "verification"), ("planning", None),
                  (None, "planning"), ("ambiguous_other", "ambiguous_other")]
        rows = [{"item_id": str(index), "root_id": "r" + str(index), "reference_role": left,
                 "new_role": right, "technical_status": "valid" if right is not None else "invalid"}
                for index, (left, right) in enumerate(labels)]
        metrics = pair_metrics(rows)
        self.assertEqual(metrics["planned_items"], 5)
        self.assertEqual(metrics["valid_pairs"], 3)
        self.assertEqual(metrics["matches"], 2)
        self.assertEqual(metrics["invalid_or_unresolved"], 2)
        self.assertAlmostEqual(metrics["raw_agreement"], 2 / 3)
        self.assertAlmostEqual(metrics["agreement_over_planned"], 2 / 5)
        wholly_invalid = pair_metrics([{**row, "new_role": None, "technical_status": "invalid"} for row in rows])
        self.assertEqual(wholly_invalid["planned_items"], 5)
        self.assertEqual(wholly_invalid["valid_pairs"], 0)
        self.assertEqual(wholly_invalid["matches"], 0)
        self.assertEqual(wholly_invalid["invalid_or_unresolved"], 5)
        self.assertIsNone(wholly_invalid["raw_agreement"])
        self.assertIsNone(wholly_invalid["cohen_kappa"])
        degenerate = pair_metrics([{**row, "reference_role": "planning", "new_role": "planning"} for row in rows])
        self.assertEqual(degenerate["raw_agreement"], 1)
        self.assertIsNone(degenerate["cohen_kappa"])


class CrossModelCollectorSafetyTests(unittest.TestCase):
    """Temporary journals and fake transports only; never real credentials."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cross-model-collector-test-")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.base = self.project / ARTIFACT
        self.state = self.project / ".research/resumption-2026-11-08-live"
        self.state.mkdir(parents=True)
        prompt_items = []
        for index in range(72):
            value = item()
            value["item_id"] = f"synthetic-collector-item-{index}"
            value["current_segment"]["source_id"] = value["item_id"]
            value["previous_segments"][0]["source_id"] = value["item_id"] + ":past:0"
            prompt_items.append(value)
        self.document = {"items": prompt_items, "ablation_ids": [value["item_id"] for value in prompt_items[:24]]}
        write(self.base / "input-items.json", self.document)
        write(self.base / "codebook.json", read(PARENT / "codebook.json"))
        write(self.base / "parent-integrity.json", {"files": {}})
        # Published closed rows are copied into the isolated temporary project.
        # No test opens or modifies the actual shared live journal.
        write(self.state / "ledger.json", read(PARENT / "ledger-final.json"))
        for model, _provider in ROUTES:
            name = model.replace("/", "_") + ".json"
            write(self.base / "metadata" / name, read(OUTPUT / "metadata" / name))
        write(self.project / PROTOCOL, {"frozen_files": {}, "execution": {"dispatch_deadline_utc": "2099-01-01T00:00:00+00:00"}})
        self.calls = []

    def no_external_transport(self, path, **kwargs):
        self.calls.append((path, kwargs))
        raise AssertionError("External transport must never be called by this test")

    def collector(self, transport=None):
        quote(self.project)
        collector = Collector(self.project, transport=transport or self.no_external_transport)
        # Windows' default temporary directory is longer than the real project
        # checkout; keep test call paths below MAX_PATH without touching state.
        collector.scope = self.project / "scope"
        return collector

    def fake_authorize(self, collector):
        # Bypass only for explicitly fake transport tests; no authorization file
        # or imitation user approval is written to disk.
        collector.authorize = lambda: setattr(collector, "key", "synthetic-test-credential")

    def test_quote_and_fixed_roster_are_keyless_and_contain_exactly_194_calls(self):
        before = (self.state / "ledger.json").read_bytes()
        with patch("cross_model.runner.http", side_effect=AssertionError("Quote must remain offline")):
            quoted = quote(self.project)
        self.assertEqual(quoted["paid_requests"], 0)
        self.assertEqual(quoted["maximum_new_calls"], 194)
        self.assertEqual((self.state / "ledger.json").read_bytes(), before)
        roster = cells(self.document, read(self.base / "codebook.json"))
        self.assertEqual(len(roster), 194)
        self.assertEqual(Counter(value["condition"] for value in roster),
                         {"schema_probe": 2, "full_context": 144, "without_context": 48})
        self.assertEqual(len({(value["model"], value["condition"], value["item_id"]) for value in roster}), 194)
        self.assertFalse((self.project / ".env").exists())
        self.assertEqual(self.calls, [])

    def test_missing_budget_authorization_stops_before_transport_or_new_ledger_rows(self):
        collector = self.collector()
        before = (self.state / "ledger.json").read_bytes()
        with self.assertRaises((ValueError, FileNotFoundError)):
            collector.collect()
        with self.assertRaises((ValueError, FileNotFoundError)):
            collector.attempt(collector.roster[0])
        self.assertEqual(self.calls, [])
        self.assertEqual((self.state / "ledger.json").read_bytes(), before)
        self.assertFalse(collector.scope.exists())

    def test_transport_failure_is_reserved_once_and_never_automatically_resent(self):
        def failing_transport(path, **kwargs):
            self.calls.append(path)
            raise TimeoutError("synthetic transport failure")
        collector = self.collector(failing_transport)
        self.fake_authorize(collector)
        original = read(self.state / "ledger.json")
        first = collector.attempt(collector.roster[0])
        second = collector.attempt(collector.roster[0])
        self.assertEqual(first, second)
        self.assertNotEqual(first["technical_status"], "valid")
        self.assertIsNone(first["vote"])
        self.assertEqual(self.calls, ["/chat/completions"])
        after = read(self.state / "ledger.json")
        self.assertEqual(after[:-1], original)
        self.assertEqual(after[-1]["state"], "unknown")
        self.assertEqual(after[-1]["charged_or_reserved_rub"], after[-1]["reservation_rub"])

    def test_budget_exhaustion_stops_before_transport_and_keeps_history(self):
        collector = self.collector()
        self.fake_authorize(collector)
        collector.cap = collector.launch_amount
        before = (self.state / "ledger.json").read_bytes()
        with self.assertRaises(RuntimeError):
            collector.attempt(collector.roster[0])
        self.assertEqual(self.calls, [])
        self.assertEqual((self.state / "ledger.json").read_bytes(), before)

    def test_nonobject_payload_becomes_invalid_without_losing_budget_reservation(self):
        def malformed_transport(path, **kwargs):
            self.calls.append(path)
            return {"http_status": 200, "json": []}
        collector = self.collector(malformed_transport)
        self.fake_authorize(collector)
        original = read(self.state / "ledger.json")
        result = collector.attempt(collector.roster[0])
        self.assertNotEqual(result["technical_status"], "valid")
        self.assertIsNone(result["vote"])
        after = read(self.state / "ledger.json")
        self.assertEqual(after[:-1], original)
        self.assertEqual(after[-1]["charged_or_reserved_rub"], after[-1]["reservation_rub"])
        self.assertEqual(self.calls, ["/chat/completions"])

    def test_annotation_cache_corruption_is_detected_without_resending(self):
        def invalid_transport(path, **kwargs):
            self.calls.append(path)
            return {"http_status": 503, "json": {"error": {"message": "synthetic failure"}}}
        collector = self.collector(invalid_transport)
        self.fake_authorize(collector)
        result = collector.attempt(collector.roster[0])
        result_path = collector.scope / "calls" / result["call_id"] / "result.json"
        corrupted = {**result, "technical_status": "valid", "vote": vote()}
        write(result_path, corrupted)
        before = (self.state / "ledger.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "Cached annotation"):
            collector.attempt(collector.roster[0])
        self.assertEqual(self.calls, ["/chat/completions"])
        self.assertEqual((self.state / "ledger.json").read_bytes(), before)

    def test_unfinished_attempt_directory_is_never_resent_or_rereserved(self):
        def invalid_transport(path, **kwargs):
            self.calls.append(path)
            raise TimeoutError("synthetic interruption")
        collector = self.collector(invalid_transport)
        self.fake_authorize(collector)
        result = collector.attempt(collector.roster[0])
        result_path = collector.scope / "calls" / result["call_id"] / "result.json"
        result_path.unlink()  # This exact path belongs to this test's temporary project.
        before = (self.state / "ledger.json").read_bytes()
        recovered = collector.attempt(collector.roster[0])
        self.assertEqual(recovered["technical_status"], "unknown")
        self.assertEqual(recovered["invalid_reason"], "previous_attempt_never_resent")
        self.assertIsNone(recovered["vote"])
        self.assertEqual(self.calls, ["/chat/completions"])
        self.assertEqual((self.state / "ledger.json").read_bytes(), before)

    def test_reflected_test_credential_is_redacted_before_writing_raw_response(self):
        key = "synthetic-test-credential"
        def reflecting_transport(path, **kwargs):
            return {"http_status": 401, "json": {"error": {"message": "Bearer " + key}}, "raw_body": key}
        collector = self.collector(reflecting_transport)
        self.fake_authorize(collector)
        result = collector.attempt(collector.roster[0])
        directory = collector.scope / "calls" / result["call_id"]
        for path in directory.iterdir():
            self.assertNotIn(key.encode(), path.read_bytes())
        self.assertIn(b"[REDACTED]", (directory / "response.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
