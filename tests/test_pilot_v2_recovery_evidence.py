"""Synthetic sealed-A -> R1 delta/replay, with no model API access.

Archive fixtures use a serial scheduler. They do not test concurrent collection.
Windows CI exposed a real unlocked-ledger-reader/replace race in the frozen R1
collector; it is documented in PILOT_V2_WINDOWS_IO_COMPATIBILITY.md and tested
separately by test_pilot_v2_ledger_io_compat.py. Measured sources stay unchanged.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


EXPORT = module(ROOT / "scripts/export_pilot_v2_recovery.py", "test_R1_export")
REPLAY = module(ROOT / "scripts/reproduce_pilot_v2_recovery.py", "test_R1_replay")
FIXTURES = module(ROOT / "tests/test_pilot_v2_recovery.py", "test_R1_evidence_fixtures")
STATS = module(ROOT / "pilot_v2/statistical_design.py", "test_R1_stats")


def support(runner, results, path):
    value = STATS.summarize_support(results["records"], runner.tasks, [row["model"] for row in runner.protocol["models"]])
    value["input_sha256"] = {"records": EXPORT.sha((runner.scope / "results.json").read_bytes()), "tasks": runner.tasks_digest}
    path.write_bytes(STATS.canonical(value) + b"\n")


def serial_archive_fixture_run(runner):
    """Only synthetic journal creation; preserve the frozen collector itself."""
    collector = sys.modules[FIXTURES.RecoveryRunner.__module__]
    def serial_executor(*args, **kwargs):
        return ThreadPoolExecutor(max_workers=1)
    with patch.object(collector, "ThreadPoolExecutor", serial_executor):
        return runner.run()


def fixture():
    item = FIXTURES.RecoveryTests()
    original = FIXTURES.fixtures.PilotV2RunnerTests.setUp
    def prepare(target):
        original(target)
        code = ('"""Synthetic fixture, no scientific labels."""\n'
                'def verify_answer(task, text):\n'
                '    return {"verdict":"correct","correct":True,"gradable":True,"verifier_id":"synthetic-fixture-only"}\n')
        (target.project / "pilot_v2/tasks.py").write_bytes(code.replace("\n", "\r\n").encode())
        (target.project / "pilot_v2/statistical_design.py").write_bytes((ROOT / "pilot_v2/statistical_design.py").read_bytes())
        target.protocol["measurement"]["observed_prefix_words"] = [128, 256, 512]
        target.protocol["parent"]["v1_raw_bundle_manifest_sha256"] = "a" * 64
        target.protocol_path.write_bytes(EXPORT.encoded(target.protocol))
    with patch.object(FIXTURES.fixtures.PilotV2RunnerTests, "setUp", prepare):
        item.setUp()
    for name in ("export_pilot_v2", "reproduce_pilot_v2", "export_local_evidence",
                 "export_pilot_v2_recovery", "reproduce_pilot_v2_recovery",
                 "summarize_pilot_v2", "summarize_pilot_v2_recovery"):
        (item.project / "scripts" / (name + ".py")).write_bytes((ROOT / "scripts" / (name + ".py")).read_bytes())
    a_support = item.project / "support-A.json"
    support(item.a, item.a_output, a_support)
    parent = item.project / "bundle-A"
    EXPORT.A.export_delta(item.state, item.protocol_path, a_support, parent, project=item.project)
    item.parent_manifest = parent / "manifest.json"
    item.r_protocol["recovery"]["parent_delta_manifest_sha256"] = EXPORT.sha(item.parent_manifest.read_bytes())
    item.r_path.write_bytes(EXPORT.encoded(item.r_protocol))
    return item


class RecoveryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.item = fixture()
        cls.runner = cls.item.recovery()
        cls.results = serial_archive_fixture_run(cls.runner)
        cls.support = cls.item.project / "support-R1.json"
        support(cls.runner, cls.results, cls.support)
        cls.bundle = cls.item.project / "bundle-R1"
        EXPORT.export_recovery(cls.item.state, cls.item.r_path, cls.support, cls.item.parent_manifest,
                               cls.bundle, project=cls.item.project, secrets=("fixture-key",))

    @classmethod
    def tearDownClass(cls):
        cls.item.doCleanups()

    def test_selfcontained_A_then_R1_exact_physical_replay_no_network_or_state_mutation(self):
        before = {path.relative_to(self.item.state).as_posix(): EXPORT.sha(path.read_bytes())
                  for path in self.item.state.rglob("*") if path.is_file()}
        receipt = REPLAY.reproduce(self.bundle / "manifest.json", self.item.project / "replay")
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["network_attempts"], 0)
        self.assertEqual(receipt["reused_A_DeepSeek_records_exact"], 96)
        self.assertEqual(receipt["new_GPT_finalized_calls"], 96)
        self.assertEqual(receipt["legacy_physical_phase_records_explicit"], 96)
        self.assertTrue(receipt["primary_A_preserved"])
        self.assertTrue(receipt["results_exact"])
        self.assertTrue(receipt["class_support_exact"])
        self.assertIsNone(receipt["selected_common_output_cap"])
        self.assertEqual(before, {path.relative_to(self.item.state).as_posix(): EXPORT.sha(path.read_bytes())
                                  for path in self.item.state.rglob("*") if path.is_file()})
        self.assertIn(b"\r\n", (self.item.project / "replay/unpacked/project/pilot_v2/tasks.py").read_bytes())
        portable = self.item.project / "replay/unpacked/project/scripts/reproduce_pilot_v2_recovery.py"
        command = [sys.executable, "-X", "utf8", str(portable), "--manifest", str(self.bundle / "manifest.json"),
                   "--output", str(self.item.project / "portable-replay")]
        result = subprocess.run(command, cwd=self.item.project, capture_output=True, text=True, encoding="utf-8", timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["network_attempts"], 0)

    def test_hash_path_and_altered_reuse_ledger_or_mapping_fail_closed(self):
        parent_output = self.item.project / "parent-for-negative"
        REPLAY.A.reproduce(self.item.parent_manifest, parent_output)
        manifest = json.loads((self.bundle / "manifest.json").read_bytes())
        for label in ("reuse", "ledger", "mapping", "registry"):
            output = self.item.project / ("bad-" + label)
            EXPORT.verify_recovery(self.bundle / "manifest.json", output / "unpacked")
            unpacked = output / "unpacked"
            scope = unpacked / manifest["payload"]["namespace"]
            if label == "reuse":
                path = scope / "results.json"
                data = json.loads(path.read_bytes())
                row = next(row for row in data["records"] if row["model"] == REPLAY.DS)
                row["correct"] = not row["correct"]
            elif label == "ledger":
                path = unpacked / "state/ledger.json"
                data = json.loads(path.read_bytes())
                data[0]["charged_or_reserved_rub"] = "0"
            elif label == "mapping":
                path = scope / "reuse-mapping.json"
                data = json.loads(path.read_bytes())
                data["new_records"][0]["parent_trace_id"] = "0" * 64
            else:
                path = unpacked / "state/pilot-v2-recovery/condition-R1.json"
                data = json.loads(path.read_bytes())
                data["protocol_sha256"] = "0" * 64
            path.write_bytes(EXPORT.encoded(data))
            with self.subTest(label=label), self.assertRaises(REPLAY.A.ReplayError):
                REPLAY.replay_recovery(unpacked, output, manifest, parent_output)
        for path in ("../bad", "state/.. /outside", "state/NUL.json", "C:/outside"):
            with self.assertRaises(EXPORT.A.DeltaError):
                EXPORT.safe_relative(path)
        bad = self.item.project / "bad-zip"
        bad.mkdir()
        raw = bytearray((self.bundle / "evidence.zip").read_bytes())
        raw[90] ^= 1
        (bad / "evidence.zip").write_bytes(raw)
        (bad / "manifest.json").write_bytes((self.bundle / "manifest.json").read_bytes())
        with self.assertRaisesRegex(EXPORT.A.DeltaError, "hash/size"):
            EXPORT.verify_recovery(bad / "manifest.json", bad / "unpack")
        self.assertFalse((bad / "unpack").exists())

    def test_unknown_new_condition_is_replayed_without_resend_or_selecting_cap(self):
        item = fixture()
        try:
            item.akash_mode = "unknown"
            runner = item.recovery()
            results = serial_archive_fixture_run(runner)
            count = len(item.akash_paid)
            self.assertGreater(count, 0)
            self.assertLess(count, 96)
            ledger_bytes = (item.state / "ledger.json").read_bytes()
            runner.settings.key, runner.settings.deadline = "", "2000-01-01T00:00:00+00:00"
            results = serial_archive_fixture_run(runner)
            self.assertEqual(len(item.akash_paid), count)
            self.assertEqual((item.state / "ledger.json").read_bytes(), ledger_bytes)
            support_path = item.project / "support-R1.json"
            support(runner, results, support_path)
            bundle = item.project / "R1-bundle"
            EXPORT.export_recovery(item.state, item.r_path, support_path, item.parent_manifest, bundle, project=item.project)
            receipt = REPLAY.reproduce(bundle / "manifest.json", item.project / "replay")
            self.assertEqual(receipt["network_attempts"], 0)
            self.assertEqual(receipt["new_GPT_finalized_calls"], count)
            self.assertEqual(receipt["new_GPT_not_dispatched"], 96 - count)
            self.assertFalse(receipt["entire_fixed_roster_resolved"])
            self.assertIsNone(receipt["selected_common_output_cap"])
            self.assertEqual(len(item.akash_paid), count)
            self.assertEqual((item.state / "ledger.json").read_bytes(), ledger_bytes)
        finally:
            item.doCleanups()


if __name__ == "__main__":
    unittest.main()
