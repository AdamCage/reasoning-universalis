"""Synthetic lossless delta/offline replay; no paid requests or scientific data."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


exporter = module(ROOT / "scripts/export_pilot_v2.py", "test_pilot_v2_exporter")
replayer = module(ROOT / "scripts/reproduce_pilot_v2.py", "test_pilot_v2_replayer")
fixtures = module(ROOT / "tests/test_pilot_v2_runner.py", "test_pilot_v2_evidence_fixtures")


class PilotV2EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixtures.PilotV2RunnerTests()
        cls.fixture.setUp()
        cls.project, cls.state = cls.fixture.project, cls.fixture.state
        (cls.project / "pilot_v2/statistical_design.py").write_bytes((ROOT / "pilot_v2/statistical_design.py").read_bytes())
        code = ('"""Synthetic local verifier only."""\n'
                'def verify_answer(task, text):\n'
                '    return {"verdict": "correct", "correct": True, "gradable": True, '
                '"verifier_id": "synthetic-fixture-only"}\n')
        (cls.project / "pilot_v2/tasks.py").write_bytes(code.replace("\n", "\r\n").encode("utf-8"))
        cls.fixture.protocol["measurement"]["observed_prefix_words"] = [128, 256, 512]
        cls.fixture.protocol["parent"]["v1_raw_bundle_manifest_sha256"] = "a" * 64
        cls.fixture.protocol_path.write_bytes(exporter.encoded(cls.fixture.protocol))
        cls.runner = cls.fixture.runner()
        cls.runner.run()
        stats = module(ROOT / "pilot_v2/statistical_design.py", "test_pilot_v2_evidence_stats")
        records = json.loads((cls.runner.scope / "results.json").read_bytes())
        tasks = json.loads(cls.fixture.tasks_path.read_bytes())["tasks"]
        support = stats.summarize_support(records["records"], tasks, list(cls.runner.model_specs),
                                          output_budgets=(2048, 8192), prefix_budgets=(128, 256, 512))
        support["input_sha256"] = {"records": exporter.sha((cls.runner.scope / "results.json").read_bytes()),
                                   "tasks": exporter.sha(cls.fixture.tasks_path.read_bytes())}
        cls.support_path = cls.project / "support.json"
        cls.support_path.write_bytes(stats.canonical(support) + b"\n")
        cls.bundle = cls.project / "bundle"
        cls.export_result = exporter.export_delta(cls.state, cls.fixture.protocol_path, cls.support_path,
                                                  cls.bundle, project=cls.project, secrets=("fixture-key",))

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()

    def test_exact_frozen_raw_replay_and_constant_labels_do_not_select_cap(self):
        before = {path.relative_to(self.state).as_posix(): exporter.sha(path.read_bytes())
                  for path in self.state.rglob("*") if path.is_file()}
        receipt = replayer.reproduce(self.bundle / "manifest.json", self.project / "replay")
        self.assertEqual(receipt["network_attempts"], 0)
        self.assertTrue(receipt["results_exact"])
        self.assertTrue(receipt["class_support_exact"])
        self.assertEqual(receipt["raw_finalized_calls"], 192)
        self.assertIsNone(receipt["selected_common_output_cap"])
        self.assertEqual(receipt["scientific_validity"], "not_assessed")
        self.assertEqual(before, {path.relative_to(self.state).as_posix(): exporter.sha(path.read_bytes())
                                  for path in self.state.rglob("*") if path.is_file()})
        frozen = self.project / "replay/unpacked/project/pilot_v2/tasks.py"
        self.assertIn(b"\r\n", frozen.read_bytes())
        self.assertEqual(frozen.read_bytes(), (self.project / "pilot_v2/tasks.py").read_bytes())

    def test_hash_tampering_and_path_traversal_are_rejected_before_unpack(self):
        manifest = json.loads((self.bundle / "manifest.json").read_bytes())
        bad = self.project / "bad"
        bad.mkdir()
        raw = bytearray((self.bundle / "evidence.zip").read_bytes())
        raw[90] ^= 1
        (bad / "evidence.zip").write_bytes(raw)
        (bad / "manifest.json").write_bytes(exporter.encoded(manifest))
        with self.assertRaisesRegex(exporter.DeltaError, "hash/size"):
            exporter.verify_delta(bad / "manifest.json", bad / "unpack")
        self.assertFalse((bad / "unpack").exists())
        for name in ("../outside", "state/../outside", "state/.. /outside", "state/NUL.json",
                     "state/directory./file", "C:/outside", "state\\bad", "/absolute"):
            with self.assertRaises(exporter.DeltaError):
                exporter.safe_relative(name)

    def test_secret_scan_including_base64_raw_body_blocks_export(self):
        import base64
        path = self.runner.scope / "metadata/history" / ("f" * 64 + ".json")
        path.write_bytes(exporter.encoded({"response": {"body_base64": base64.b64encode(b"fixture-key").decode()}}))
        try:
            with self.assertRaises(Exception):
                exporter.export_delta(self.state, self.fixture.protocol_path, self.support_path,
                                      self.project / "secret-bundle", project=self.project, secrets=("fixture-key",))
        finally:
            path.unlink()
        self.assertFalse((self.project / "secret-bundle").exists())

    def test_socket_guard_blocks_and_records_connections(self):
        import socket
        with replayer.socket_guard() as calls:
            with self.assertRaisesRegex(replayer.ReplayError, "Network"):
                socket.create_connection(("example.invalid", 443))
        self.assertEqual(len(calls), 1)

    def test_regenerated_labels_source_bytes_and_retained_ledger_fail_closed(self):
        for label in ("label", "source", "ledger"):
            output = self.project / ("tampered-" + label)
            exporter.verify_delta(self.bundle / "manifest.json", output / "unpacked")
            unpacked = output / "unpacked"
            manifest = json.loads((self.bundle / "manifest.json").read_bytes())
            scope = unpacked / manifest["payload"]["namespace"]
            if label == "label":
                path = scope / "results.json"
                document = json.loads(path.read_bytes())
                document["records"][0]["correct"] = False
                path.write_bytes(exporter.encoded(document))
            elif label == "source":
                path = scope / "source/pilot_v2/tasks.py"
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
            else:
                path = unpacked / "state/ledger.json"
                document = json.loads(path.read_bytes())
                document[0]["charged_or_reserved_rub"] = "0"
                path.write_bytes(exporter.encoded(document))
            with self.subTest(label=label), self.assertRaises(replayer.ReplayError):
                replayer.replay_unpacked(unpacked, output, manifest)

    def test_unknown_reserves_and_full_unsent_denominator_replay_without_retry(self):
        fixture = fixtures.PilotV2RunnerTests()
        fixture.setUp()
        try:
            (fixture.project / "pilot_v2/statistical_design.py").write_bytes((ROOT / "pilot_v2/statistical_design.py").read_bytes())
            (fixture.project / "pilot_v2/tasks.py").write_bytes((self.project / "pilot_v2/tasks.py").read_bytes())
            fixture.protocol["measurement"]["observed_prefix_words"] = [128, 256, 512]
            fixture.protocol["parent"]["v1_raw_bundle_manifest_sha256"] = "a" * 64
            fixture.protocol_path.write_bytes(exporter.encoded(fixture.protocol))
            fixture.transport.mode = "unknown"
            runner = fixture.runner()
            results = runner.run()
            attempted = len(fixture.transport.paid)
            self.assertGreater(attempted, 0)
            self.assertLess(attempted, 192)
            stats = module(ROOT / "pilot_v2/statistical_design.py", "test_unknown_support")
            support = stats.summarize_support(results["records"], runner.tasks, list(runner.model_specs))
            support_path = fixture.project / "support.json"
            support_path.write_bytes(stats.canonical(support) + b"\n")
            bundle = fixture.project / "bundle"
            exporter.export_delta(fixture.state, fixture.protocol_path, support_path, bundle, project=fixture.project)
            receipt = replayer.reproduce(bundle / "manifest.json", fixture.project / "replay")
            self.assertEqual(receipt["network_attempts"], 0)
            self.assertEqual(receipt["raw_finalized_calls"], attempted)
            self.assertEqual(receipt["not_dispatched"], 192 - attempted)
            self.assertFalse(receipt["entire_fixed_roster_resolved"])
            self.assertIsNone(receipt["selected_common_output_cap"])
            self.assertEqual(len(fixture.transport.paid), attempted)
            self.assertTrue(all(row["state"] == "unknown" for row in
                                json.loads((fixture.state / "ledger.json").read_bytes())[len(fixture.launch_rows):]))
        finally:
            fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
