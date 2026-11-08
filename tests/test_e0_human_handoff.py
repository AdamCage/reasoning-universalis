"""Synthetic tests only; no human identities, annotations or approval created."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


PREP, IMPORT = module("prepare_e0_human"), module("import_e0_human")


class HumanHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tasks, records = [], []
        for root in range(24):
            for variant in range(2):
                task_id = "task-" + str(root) + "-" + str(variant)
                tasks.append({"task_id": task_id, "root_id": "root-" + str(root), "domain": "fixture",
                              "prompt": "Solve the supplied fixture.", "split": "development", "confirmatory_excluded": True})
                for model in ("fixture-model-one", "fixture-model-two"):
                    for budget in (2048, 8192):
                        identity = PREP.rank(root, variant, model, budget)
                        text = ("Plan α.\r\nCompute β.\r\nCheck γ.\r\n" * 8) + "ANSWER: 5."
                        records.append({"trace_id": identity, "task_id": task_id, "root_id": "root-" + str(root),
                            "model": model, "provider": "fixture-provider", "raw_reasoning_text": text,
                            "raw_reasoning_sha256": PREP.sha(text.encode()), "request_sha256": "a" * 64,
                            "response_sha256": "b" * 64, "protocol_sha256": "c" * 64,
                            "status": "completed", "correct": True, "output_budget_tokens": budget})
        self.results = {"phase": "pilot_v2_provider_recovery_R1", "all_planned_cells": 192, "records": records}
        self.tasks = {"tasks": tasks}
        self.result_path, self.task_path, self.proof_path = (self.root / name for name in ("results.json", "tasks.json", "proof.json"))
        PREP.write(self.task_path, self.tasks)
        self.results["corpus_sha256"] = PREP.sha(self.task_path.read_bytes())
        PREP.write(self.result_path, self.results)
        self.proof()
        self.package = self.root / "package"
        PREP.build(self.result_path, self.task_path, self.proof_path, self.package, synthetic=True)

    def proof(self):
        PREP.write(self.proof_path, {"status": "passed", "network_attempts": 0, "synthetic_fixture": True,
                                   "results_sha256": PREP.sha(self.result_path.read_bytes())})

    def submitted(self, slot, round_name):
        directory = (self.package / "public-boundary" / slot if round_name == "boundaries"
                     else self.package / "coordinator/role-round2-prepared" / slot)
        value = PREP.load(directory / "responses.empty.json")
        value["status"] = "completed"
        actor = value["human_attestation"]
        for key in actor:
            actor[key] = True
        actor["participant_pseudonym"] = "SYNTHETIC-FIXTURE-ONLY-" + slot
        actor["completed_utc"] = "2026-11-08T20:00:00+00:00" if round_name == "boundaries" else "2026-11-08T21:00:00+00:00"
        for row in value["responses"]:
            row.update(completed=True, comment="")
            if round_name == "boundaries":
                row.update(boundaries=[7], uncertain_boundaries=[])
            else:
                packet = PREP.load(directory / "items.json")
                item = next(item for item in packet["items"] if item["item_id"] == row["item_id"])
                row.update(primary_role="planning", secondary_roles=[], confidence="low", reason_code="strategy",
                           explanation="Synthetic test of the importer only, never human data.",
                           evidence_quotes=[{"source_id": row["item_id"], "quote": item["current_segment"]["text"][:20]}],
                           context_extended=False)
        path = self.root / (slot + "-" + round_name + ".json")
        PREP.write(path, value)
        return path

    def test_package_empty_and_masked_exact_CRLF_no_human_or_E0_claim(self):
        root, manifest, mapping = IMPORT.check_package(self.package)
        ready = PREP.load(self.package / "readiness.json")
        self.assertEqual(ready["E0"], "pending")
        self.assertEqual(ready["independent_measurement_validation_roots"], 0)
        self.assertEqual(ready["root_shortfall_even_before_independence"], 16)
        self.assertEqual(len(mapping["traces"]), 24)
        self.assertEqual(len(mapping["roles_s2"]), 200)
        packet = PREP.load(self.package / "public-boundary/A/items.json")
        self.assertTrue(all("\r\n" in item["text"] and "ANSWER:" in item["text"] for item in packet["items"]))
        self.assertTrue(all(set(item) == {"item_id", "problem_statement", "text", "text_sha256"} for item in packet["items"]))
        for slot in ("A", "B"):
            form = PREP.load(self.package / "public-boundary" / slot / "responses.empty.json")
            self.assertTrue(all(value is None for value in form["human_attestation"].values()))
            self.assertTrue(all(row["boundaries"] is None and row["completed"] is None for row in form["responses"]))
        self.assertEqual(PREP.load(self.package / "coordinator/gold.empty.json")["labels"], [])

    def test_choice_does_not_depend_on_correctness_or_input_order(self):
        self.results["records"].reverse()
        for row in self.results["records"]:
            row["correct"] = False
        PREP.write(self.result_path, self.results)
        self.proof()
        other = self.root / "other-package"
        PREP.build(self.result_path, self.task_path, self.proof_path, other, synthetic=True)
        a, b = (PREP.load(path / "coordinator/source-map.json") for path in (self.package, other))
        self.assertEqual(a, b)

    def test_rebuild_has_no_timestamps_and_identical_LF_files_and_portable_source_paths(self):
        other = self.root / "same-input-rebuild"
        PREP.build(self.result_path, self.task_path, self.proof_path, other, synthetic=True)
        first = {path.relative_to(self.package).as_posix(): path.read_bytes()
                 for path in self.package.rglob("*") if path.is_file()}
        second = {path.relative_to(other).as_posix(): path.read_bytes() for path in other.rglob("*") if path.is_file()}
        self.assertEqual(first, second)
        self.assertTrue(all(b"\r" not in data for name, data in first.items() if not name.endswith(".zip")))
        sources = PREP.load(other / "coordinator/source-provenance.json")["sources"]
        self.assertTrue(all("\\" not in value["path"] for value in sources.values()))

    def test_blank_or_same_actor_cannot_release_and_first_submission_can_be_sealed(self):
        with self.assertRaises(ValueError):
            IMPORT.release_roles(self.package, self.package / "public-boundary/A/responses.empty.json",
                                 self.package / "public-boundary/B/responses.empty.json", self.root / "no-release")
        a, b = self.submitted("A", "boundaries"), self.submitted("B", "boundaries")
        receipt = IMPORT.record_one(self.package, "A", "boundaries", a, self.root / "first-only")
        self.assertEqual(receipt["agreement"], "not_evaluated")
        same = PREP.load(b)
        same["human_attestation"]["participant_pseudonym"] = PREP.load(a)["human_attestation"]["participant_pseudonym"]
        PREP.write(b, same)
        with self.assertRaises(ValueError):
            IMPORT.release_roles(self.package, a, b, self.root / "same-person")

    def test_synthetic_boundary_then_S2_roles_preserve_undefined_kappa_and_pending_E0(self):
        a, b = self.submitted("A", "boundaries"), self.submitted("B", "boundaries")
        released = self.root / "released"
        result = IMPORT.release_roles(self.package, a, b, released, synthetic_released_utc="2026-11-08T20:30:00+00:00")
        self.assertEqual(result["status"], "synthetic_fixture_only")
        role_a, role_b = self.submitted("A", PREP.ROLE_ROUND), self.submitted("B", PREP.ROLE_ROUND)
        with self.assertRaises(ValueError):
            IMPORT.import_pair(self.package, PREP.ROLE_ROUND, role_a, role_b, self.root / "no-boundary-receipt")
        result = IMPORT.import_pair(self.package, PREP.ROLE_ROUND, role_a, role_b,
                                   self.root / "imported", released / "release-receipt.private.json")
        self.assertEqual(result["status"], "synthetic_fixture_not_human_data")
        self.assertFalse(result["human_identity_verified"])
        value = PREP.load(self.root / "imported/pre-adjudication.private.json")
        self.assertEqual(value["E0"], "pending")
        self.assertIsNone(value["metrics"]["cohen_kappa"])
        self.assertTrue(value["metrics"]["degenerate_marginals"])
        self.assertIsNone(value["metrics"]["macro_f1_against_adjudicated_human_gold"])
        self.assertEqual(value["metrics"]["root_bootstrap"]["roots"], 24)
        self.assertIsNone(value["metrics"]["root_bootstrap"]["cohen_kappa_interval"])
        self.assertEqual(value["adjudication"], "not_started")

    def test_tampered_packet_missing_labels_false_quotes_and_nonhuman_claims_refused(self):
        root, manifest, mapping = IMPORT.check_package(self.package)
        path = self.submitted("A", PREP.ROLE_ROUND)
        original = PREP.load(path)
        variants = []
        value = copy.deepcopy(original)
        value["responses"].pop()
        variants.append(value)
        value = copy.deepcopy(original)
        value["responses"][0]["primary_role"] = None
        variants.append(value)
        value = copy.deepcopy(original)
        value["responses"][0]["evidence_quotes"][0]["quote"] = "not present anywhere"
        variants.append(value)
        value = copy.deepcopy(original)
        value["human_attestation"]["is_human"] = False
        variants.append(value)
        value = copy.deepcopy(original)
        value["human_attestation"]["no_role_round_access_before_boundary"] = False
        variants.append(value)
        for value in variants:
            PREP.write(path, value)
            with self.assertRaises(ValueError):
                IMPORT.validate(root, manifest, "A", PREP.ROLE_ROUND, path)
        packet = self.package / "public-boundary/A/items.json"
        packet.write_bytes(packet.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            IMPORT.check_package(self.package)

    def test_role_completion_cannot_precede_the_other_persons_boundary_submission(self):
        a, b = self.submitted("A", "boundaries"), self.submitted("B", "boundaries")
        other = PREP.load(b)
        other["human_attestation"]["completed_utc"] = "2026-11-08T22:00:00+00:00"
        PREP.write(b, other)
        release = self.root / "late-boundary-release"
        IMPORT.release_roles(self.package, a, b, release, synthetic_released_utc="2026-11-08T22:30:00+00:00")
        role_a, role_b = self.submitted("A", PREP.ROLE_ROUND), self.submitted("B", PREP.ROLE_ROUND)
        later = PREP.load(role_b)
        later["human_attestation"]["completed_utc"] = "2026-11-08T23:00:00+00:00"
        PREP.write(role_b, later)
        with self.assertRaisesRegex(ValueError, "both independent"):
            IMPORT.import_pair(self.package, PREP.ROLE_ROUND, role_a, role_b, self.root / "bad-order",
                               release / "release-receipt.private.json")
        valid = PREP.load(role_a)
        valid["human_attestation"]["completed_utc"] = "2026-11-08T22:10:00+00:00"
        PREP.write(role_a, valid)
        with self.assertRaisesRegex(ValueError, "actual release"):
            IMPORT.import_pair(self.package, PREP.ROLE_ROUND, role_a, role_b, self.root / "before-release",
                               release / "release-receipt.private.json")
        valid["human_attestation"]["completed_utc"] = "2026-11-08T22:30:00+00:00"
        PREP.write(role_a, valid)
        imported = IMPORT.import_pair(self.package, PREP.ROLE_ROUND, role_a, role_b, self.root / "valid-order",
                                     release / "release-receipt.private.json")
        self.assertEqual(imported["E0"], "pending")
        self.assertEqual(imported["status"], "synthetic_fixture_not_human_data")

    def test_changed_or_duplicate_task_corpus_cannot_change_human_problem_context(self):
        self.tasks["tasks"][0]["prompt"] = "Tampered task context."
        PREP.write(self.task_path, self.tasks)
        with self.assertRaisesRegex(ValueError, "corpus"):
            PREP.build(self.result_path, self.task_path, self.proof_path, self.root / "wrong-context", synthetic=True)
        self.tasks["tasks"].append(copy.deepcopy(self.tasks["tasks"][0]))
        PREP.write(self.task_path, self.tasks)
        self.results["corpus_sha256"] = PREP.sha(self.task_path.read_bytes())
        PREP.write(self.result_path, self.results)
        self.proof()
        with self.assertRaisesRegex(ValueError, "48-task"):
            PREP.build(self.result_path, self.task_path, self.proof_path, self.root / "duplicate-context", synthetic=True)

    def test_invalid_boundary_offsets_duplicate_json_and_foreign_round_refused(self):
        root, manifest, mapping = IMPORT.check_package(self.package)
        path = self.submitted("A", "boundaries")
        value = PREP.load(path)
        value["responses"][0]["boundaries"] = [True]
        PREP.write(path, value)
        with self.assertRaises(ValueError):
            IMPORT.validate(root, manifest, "A", "boundaries", path)
        path.write_text('{"same":1,"same":2}', encoding="utf-8")
        with self.assertRaises(ValueError):
            PREP.load(path)
        with self.assertRaises(ValueError):
            IMPORT.checked_relative(self.package, "../outside")

    def test_changed_runtime_method_is_not_accepted_as_LF_compatibility(self):
        evaluation = sys.modules["measurement.evaluation"]
        fake = self.root / "changed-evaluation.py"
        fake.write_bytes(Path(evaluation.__file__).read_bytes().replace(b"\r\n", b"\n") + b"\n# changed source\n")
        with patch.object(evaluation, "__file__", str(fake)), self.assertRaisesRegex(ValueError, "Runtime method source"):
            IMPORT.check_package(self.package)


if __name__ == "__main__":
    unittest.main()
