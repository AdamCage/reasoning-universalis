"""Fake new votes on a sealed real historical parent; no live-state reads/API."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from machine_development import annotation as ann
from scripts import export_machine_development as export
from scripts import reproduce_machine_development as replay
from scripts.collect_machine_development import MachineDevelopmentRunner, MachineSettings
from scripts.prepare_machine_development import snapshot_codebook
from scripts.summarize_machine_development import build as summarize
from stage0.runner import encode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_machine_development_runner import FakeAnnotationTransport


class MachineEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name).resolve()
        cls.root = root
        cls.project, cls.state = root / "project", root / "project/live"
        cls.project.mkdir()
        cls.parent_manifest = ROOT / "evidence/pilot-v2-recovery-2026-11-08/manifest.json"
        parent = root / "closed-R1"
        export.PARENT.verify_recovery(cls.parent_manifest, parent)
        old = root / "closed-A"
        export.A.verify_delta(parent / "bundle/parent-A/manifest.json", old)
        shutil.copytree(old / "state", cls.state)
        shutil.copytree(parent / "state", cls.state, dirs_exist_ok=True)
        inherited = json.loads((cls.state / "source-inventory.json").read_bytes())["files"]
        required = set(inherited) | set(export.PROGRAMS) | set(export.RUNTIME_SUPPORT) | {
            "scripts/collect_machine_development.py", "scripts/pilot_v2_ledger_io_compat_v1.py", "scripts/prepare_machine_development.py",
            "stage2/annotation.py", "stage2/observations.py", "measurement/core.py", "measurement/lexical.py",
            "design/ANNOTATION_CONFIG.json", "design/ANNOTATION_RESPONSE.schema.json", "design/ANNOTATION_PROTOCOL.md",
            "design/prompts/segment-role-v1.md", "requirements-resumption.txt"}
        required |= {path.relative_to(ROOT).as_posix() for path in (ROOT / "machine_development").glob("*.py")}
        for name in required:
            destination = cls.project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes())
        cls.inputs = cls.project / "machine-inputs"
        cls.inputs.mkdir()
        items = [{"item_id": "synthetic-" + str(index), "problem_statement": "Synthetic annotation-only fixture.",
                  "current_segment": {"source_id": "synthetic-" + str(index), "text": "Choose the next method."},
                  "previous_segments": []} for index in range(24)]
        documents = {"input-items.json": {"items": items, "audit_item_ids": ann.audit_item_ids(items)},
            "codebook.json": snapshot_codebook(cls.project),
            "machine-mapping.json": {"items": {item["item_id"]: {"root_id": "fixture-root-" + str(index)}
                                                for index, item in enumerate(items)}}}
        for name, value in documents.items():
            (cls.inputs / name).write_bytes(encode(value))
        p = json.loads((ROOT / "design/MACHINE_DEVELOPMENT_PROTOCOL_2026_11_08.json").read_bytes())
        p.update(protocol_id="synthetic-machine-evidence-not-real-annotations", synthetic_fixture=True,
                 status="prospective_frozen_machine_development")
        p["budget"]["shared_state"] = "live"
        p["generation"]["dispatch_deadline_utc"] = "2099-01-01T00:00:00+00:00"
        p["metadata"] = {"BytePlus_declared_context_length": 1048576}
        p["parent"]["machine_parent_R1_manifest_sha256"] = ann.sha(cls.parent_manifest.read_bytes())
        def spec(name):
            path = cls.inputs / name
            return {"path": path.relative_to(cls.project).as_posix(), "file_sha256": ann.sha(path.read_bytes())}
        p["inputs"] = {**spec("input-items.json"), "items": 24, "roots": 24,
                       "codebook": spec("codebook.json"), "mapping": spec("machine-mapping.json")}
        p["allocation"].update(first_round_calls=120, conditional_second_round_calls=120, audit_items=3, audit_calls=15, maximum_calls=255)
        cls.protocol = cls.project / "design/synthetic-machine-protocol.json"
        cls.protocol.write_bytes(encode(p))
        cls.zero_project = root / "zero-project"
        shutil.copytree(cls.project, cls.zero_project)
        cls.transport = FakeAnnotationTransport()
        cls.runner = MachineDevelopmentRunner(MachineSettings(state=cls.state, key="fixture-key", cap=3300,
            collection_cap=3300, top_p=1.0, max_tokens=1024), cls.protocol, cls.transport, project=cls.project, execute=True)
        cls.runner.run()
        summarize(cls.runner.scope, cls.protocol, cls.inputs / "input-items.json", cls.inputs / "codebook.json",
            cls.inputs / "machine-mapping.json", cls.state / "ledger.json", cls.inputs,
            cls.project / "reports/MACHINE_DEVELOPMENT_RESULT.md", source_root=cls.project, calls=cls.state / "calls")
        cls.bundle = root / "machine-bundle"
        export.export(cls.state, cls.protocol, cls.parent_manifest, cls.bundle, project=cls.project, secrets=("fixture-key",))

    @classmethod
    def tearDownClass(cls):
        # The nested immutable parent namespace exceeds MAX_PATH on Windows.
        # Validate this exact owned temporary target before recursive cleanup.
        target = Path(cls.temporary.name).resolve(strict=True)
        if target != cls.root or target.parent != Path(tempfile.gettempdir()).resolve(strict=True):
            raise AssertionError("Unexpected temporary cleanup target")
        shutil.rmtree(replay.native_path(target))
        cls.temporary.cleanup()

    def test_portable_archive_fresh_keyless_replay_exact_results_summary_and_parent(self):
        receipt = replay.reproduce(self.bundle / "manifest.json", Path(self.temporary.name) / "offline-replayed")
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["network_attempts"], 0)
        self.assertTrue(receipt["results_exact"] and receipt["summary_exact"])
        self.assertEqual(receipt["old_ledger_prefix_rows"], 984)
        self.assertEqual(receipt["all_planned_calls"], 255)
        self.assertEqual(receipt["E0"], "not_passed")

    def test_tampered_archive_fails_before_unpack(self):
        archive = self.bundle / "evidence.zip"
        before = archive.read_bytes()
        try:
            archive.write_bytes(before + b"tamper")
            with self.assertRaises(ValueError):
                export.verify(self.bundle / "manifest.json")
        finally:
            archive.write_bytes(before)

    def test_all_unsent_condition_without_paid_registry_remains_portable(self):
        project = self.zero_project
        state, inputs = project / "live", project / "machine-inputs"
        protocol = project / "design/synthetic-machine-protocol.json"
        transport = FakeAnnotationTransport()
        runner = MachineDevelopmentRunner(MachineSettings(state=state, key="", cap=3300, collection_cap=3300,
            top_p=1.0, max_tokens=1024), protocol, transport, project=project, execute=True)
        result = runner.run()
        self.assertEqual(transport.paid, [])
        self.assertFalse((state / "machine-development/condition-v1.json").exists())
        summarize(runner.scope, protocol, inputs / "input-items.json", inputs / "codebook.json", inputs / "machine-mapping.json",
            state / "ledger.json", inputs, project / "reports/MACHINE_DEVELOPMENT_RESULT.md", source_root=project, calls=state / "calls")
        bundle = Path(self.temporary.name) / "zero-bundle"
        export.export(state, protocol, self.parent_manifest, bundle, project=project)
        receipt = replay.reproduce(bundle / "manifest.json", Path(self.temporary.name) / "zero-replayed")
        self.assertEqual(receipt["all_planned_calls"], 255)
        self.assertEqual(receipt["old_ledger_prefix_rows"], 984)
        self.assertEqual(receipt["network_attempts"], 0)
        self.assertTrue(receipt["summary_exact"])


if __name__ == "__main__":
    unittest.main()
