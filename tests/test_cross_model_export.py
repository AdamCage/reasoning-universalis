"""Portable evidence packaging checks using isolated synthetic fixtures only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from scripts import export_cross_model as exporter


ARTIFACT = "artifacts/cross-model-2026-11-15"
PROTOCOL = "design/CROSS_MODEL_PROTOCOL_2026_11_15.json"
FORMAT = "reasoning-universalis-cross-model-evidence-v1"
COMPAT_ARTIFACT = "artifacts/cross-model-compat-2026-11-15"
COMPAT_PROTOCOL = "design/CROSS_MODEL_TRANSPORT_ADDENDUM_2026_11_15.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else encoded(value))


def read(path):
    return json.loads(path.read_bytes())


class CrossModelExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cross-model-export-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.base = self.project / ARTIFACT
        frozen_path = "cross_model/synthetic_frozen.py"
        parent_path = "artifacts/synthetic-parent/data.json"
        put(self.project / frozen_path, b"# Synthetic software fixture only.\r\n")
        put(self.project / parent_path, {"synthetic": True, "preserved": "\u03b1\r\n\U0001f44d"})
        self.protocol = {"protocol_id": "synthetic-cross-model-export-only", "status": "budget_pending",
                         "allocation": {"maximum_calls": 194}, "budget": {"new_cap_rub": "400"},
                         "frozen_files": {frozen_path: sha((self.project / frozen_path).read_bytes())}}
        put(self.project / PROTOCOL, self.protocol)
        self.protocol_digest = sha((self.project / PROTOCOL).read_bytes())
        put(self.base / "parent-integrity.json", {"files": {parent_path: sha((self.project / parent_path).read_bytes())}})
        put(self.base / "input-items.json", {"items": [{"item_id": "synthetic-item"}], "planned_items": 72})
        put(self.base / "mapping.json", {"items": {"synthetic-item": {"root_id": "synthetic-root", "char_start": 2, "char_end": 4}}})
        put(self.base / "codebook.json", {"fixture": True})
        put(self.base / "source-inventory.json", {"files": {frozen_path: self.protocol["frozen_files"][frozen_path]}})
        put(self.base / "source-snapshot.zip", b"Synthetic opaque source archive bytes.\x00\r\n")
        put(self.base / "cost-quote.json", {"paid_requests": 0, "maximum_new_calls": 194,
                                           "worst_case_reservation_rub": "0.01", "proposed_new_cap_rub": "400"})
        put(self.base / "ledger-launch.json", [{"id": "synthetic-historical-reserve", "charged_or_reserved_rub": "2.0"}])
        put(self.base / "analysis/summary.json", {"status": "offline_existing_data_only", "new_paid_calls": 0,
                                                  "cross_family": {}})
        put(self.project / "reports/CROSS_MODEL_MEASUREMENT_REPORT.md", b"# Synthetic engineering fixture\r\n")
        put(self.project / "output/pdf/cross-model-measurement-pilot.pdf", b"%PDF-1.4\n% synthetic fixture\n")
        # These files must never be selected by an evidence export.
        put(self.project / ".env", b"SYNTHETIC_SECRET=DO_NOT_PACKAGE\n")
        put(self.project / ".research/private-settings.json", {"synthetic_secret": "DO_NOT_PACKAGE"})
        put(self.project / "private/settings.json", {"synthetic_secret": "DO_NOT_PACKAGE"})
        self.output = self.root / "bundle"

    def export(self, output=None, condition="original"):
        kwargs = {"output": output or self.output}
        if condition != "original":
            kwargs["condition"] = condition
        return exporter.export(self.project, **kwargs)

    def compat_fixture(self):
        base = self.project / COMPAT_ARTIFACT
        for path in self.base.rglob("*"):
            if path.is_file() and path.name not in ("source-inventory.json", "source-snapshot.zip"):
                put(base / path.relative_to(self.base), path.read_bytes())
        quote = read(base / "cost-quote.json")
        quote["maximum_new_calls"] = 192
        put(base / "cost-quote.json", quote)
        put(self.project / "cross_model_compat.py", b"# Synthetic transport compatibility fixture.\n")
        protocol = {"protocol_id": "synthetic-transport-addendum", "parent_protocol": PROTOCOL,
                    "parent_protocol_sha256": self.protocol_digest,
                    "allocation": {"initial_probe_calls": 2, "maximum_total_calls": 194,
                                   "remaining_full_context": 144, "remaining_without_context": 48},
                    "budget": {"new_cap_rub": "400", "same_explicit_authorization": True},
                    "frozen_files": {PROTOCOL: self.protocol_digest,
                                     "cross_model_compat.py": sha((self.project / "cross_model_compat.py").read_bytes())}}
        put(self.project / COMPAT_PROTOCOL, protocol)
        return base, protocol, sha((self.project / COMPAT_PROTOCOL).read_bytes())

    def archive_members(self, output=None):
        output = output or self.output
        with zipfile.ZipFile(output / "evidence.zip") as archive:
            return {info.filename: archive.read(info.filename) for info in archive.infolist()}

    def rewrite(self, members, *, manifest_changes=None):
        """Recompute outer integrity so tests reach member/schema checks."""
        archive_path = self.output / "evidence.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in members:
                    archive.writestr(name, raw)
        manifest = read(self.output / "manifest.json")
        manifest["archive"]["bytes"] = archive_path.stat().st_size
        manifest["archive"]["sha256"] = sha(archive_path.read_bytes())
        if manifest_changes:
            manifest_changes(manifest)
        # Bind the changed payload too, so the verifier reaches the intended
        # member/path/protocol checks instead of failing at the outer JSON hash.
        if "payload_sha256" in manifest:
            manifest["payload_sha256"] = sha(exporter.encoded(manifest["payload"]))
        put(self.output / "manifest.json", manifest)

    def test_offline_export_is_deterministic_keyless_and_explicitly_unmeasured(self):
        first = self.export()
        other = self.root / "other-bundle"
        second = self.export(output=other)
        self.assertEqual(first["format"], FORMAT)
        self.assertEqual(first["payload"]["protocol_sha256"], self.protocol_digest)
        self.assertEqual(first["payload"]["annotation_state"], "no_new_annotations")
        self.assertEqual(first["payload"]["attempted_cells"], 0)
        self.assertEqual(first["payload"]["valid_annotations"], 0)
        self.assertEqual(first["payload"]["planned_calls"], 194)
        self.assertEqual((self.output / "evidence.zip").read_bytes(), (other / "evidence.zip").read_bytes())
        self.assertEqual(first, second)
        members = self.archive_members()
        expected = {PROTOCOL, ARTIFACT + "/source-snapshot.zip", ARTIFACT + "/mapping.json",
                    "cross_model/synthetic_frozen.py", "artifacts/synthetic-parent/data.json",
                    "reports/CROSS_MODEL_MEASUREMENT_REPORT.md", "output/pdf/cross-model-measurement-pilot.pdf"}
        self.assertTrue(expected <= set(members))
        self.assertFalse(any(".env" in name or ".research" in name or name.startswith("private/") for name in members))
        self.assertFalse(any(b"DO_NOT_PACKAGE" in raw for raw in members.values()))
        with zipfile.ZipFile(self.output / "evidence.zip") as archive:
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            self.assertTrue(all(info.date_time == (2026, 11, 15, 0, 0, 0) for info in archive.infolist()))
        receipt = exporter.verify(self.output / "manifest.json")
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["network_attempts"], 0)

    def test_measured_export_preserves_invalid_and_missing_cells_and_portable_raw(self):
        call_id = "a" * 64
        cells = [{"model": "fixture-model", "condition": "full_context", "item_id": f"synthetic-{index}",
                  "technical_status": "not_dispatched", "vote": None} for index in range(194)]
        cells[0].update(call_id=call_id, technical_status="invalid", invalid_reason="synthetic schema failure")
        annotations = {"protocol_sha256": self.protocol_digest, "cells": cells}
        put(self.base / "new-annotations.json", annotations)
        put(self.base / "raw" / call_id / "response.json", {"http_status": 200, "json": {"choices": []}})
        put(self.base / "raw" / call_id / "request.json", {"model": "fixture-model", "messages": []})
        put(self.base / "budget-final.json", {"additional_charged_or_reserved_rub": "0.01", "cap_additional_rub": "400"})
        manifest = self.export()
        payload = manifest["payload"]
        self.assertEqual(payload["annotation_state"], "measured")
        self.assertEqual(payload["recorded_cells"], 194)
        self.assertEqual(payload["attempted_cells"], 1)
        self.assertEqual(payload["valid_annotations"], 0)
        self.assertEqual(payload["technical_status_counts"], {"invalid": 1, "not_dispatched": 193})
        members = self.archive_members()
        self.assertEqual(json.loads(members[ARTIFACT + "/new-annotations.json"]), annotations)
        self.assertIn(ARTIFACT + "/raw/" + call_id + "/response.json", members)
        self.assertEqual(exporter.verify(self.output / "manifest.json")["status"], "passed")

    def test_all_not_dispatched_annotations_remain_explicitly_unmeasured(self):
        cells = [{"model": "fixture-model", "condition": "full_context", "item_id": f"synthetic-{index}",
                  "technical_status": "not_dispatched_probe_failed", "vote": None} for index in range(194)]
        put(self.base / "new-annotations.json", {"protocol_sha256": self.protocol_digest, "cells": cells})
        payload = self.export()["payload"]
        self.assertEqual(payload["annotation_state"], "no_new_annotations")
        self.assertEqual(payload["attempted_cells"], 0)
        self.assertEqual(payload["recorded_cells"], 194)
        self.assertEqual(payload["technical_status_counts"], {"not_dispatched_probe_failed": 194})

    def test_constructed_probe_attempts_do_not_claim_measured_study_annotations(self):
        cells = []
        for index in range(2):
            call_id = str(index + 1) * 64
            cells.append({"model": f"fixture-model-{index}", "condition": "schema_probe", "item_id": "synthetic-probe",
                          "technical_status": "invalid", "vote": None, "call_id": call_id})
            put(self.base / "raw" / call_id / "request.json", {"model": f"fixture-model-{index}", "messages": []})
        put(self.base / "new-annotations.json", {"protocol_sha256": self.protocol_digest, "cells": cells})
        payload = self.export()["payload"]
        self.assertEqual(payload["annotation_state"], "no_new_annotations")
        self.assertEqual(payload["collection_state"], "technical_probes_only")
        self.assertEqual(payload["attempted_cells"], 2)
        self.assertEqual(payload["schema_probe_attempted_cells"], 2)
        self.assertEqual(payload["study_attempted_cells"], 0)
        self.assertEqual(payload["study_valid_annotations"], 0)

    def test_unknown_partial_run_retains_missingness_without_inventing_labels(self):
        call_id = "b" * 64
        cells = [{"model": "fixture-model", "condition": "full_context", "item_id": "synthetic-unknown",
                  "technical_status": "unknown", "vote": None, "call_id": call_id}]
        put(self.base / "new-annotations.json", {"protocol_sha256": self.protocol_digest, "cells": cells})
        put(self.base / "raw" / call_id / "request.json", {"model": "fixture-model", "messages": []})
        payload = self.export()["payload"]
        self.assertEqual(payload["annotation_state"], "measured")
        self.assertEqual(payload["attempted_cells"], 1)
        self.assertEqual(payload["valid_annotations"], 0)
        self.assertEqual(payload["missing_planned_cells"], 193)
        self.assertTrue(payload["missing_raw_files"])
        self.assertEqual(exporter.verify(self.output / "manifest.json")["status"], "passed")

    def test_new_annotation_protocol_mismatch_is_rejected(self):
        put(self.base / "new-annotations.json", {"protocol_sha256": "0" * 64, "cells": []})
        with self.assertRaises(ValueError):
            self.export()

    def test_not_dispatched_cell_cannot_claim_a_physical_call_identity(self):
        cells = [{"model": "fixture-model", "condition": "full_context", "item_id": "synthetic-unknown",
                  "technical_status": "not_dispatched", "vote": None, "call_id": "c" * 64}]
        put(self.base / "new-annotations.json", {"protocol_sha256": self.protocol_digest, "cells": cells})
        put(self.base / "raw" / ("c" * 64) / "request.json", {"model": "fixture-model", "messages": []})
        with self.assertRaises(ValueError):
            self.export()

    def test_export_rejects_changed_or_missing_frozen_dependency(self):
        (self.project / "cross_model/synthetic_frozen.py").write_bytes(b"changed fixture\n")
        with self.assertRaises(ValueError):
            self.export()
        (self.project / "cross_model/synthetic_frozen.py").unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.export()

    def test_forbidden_private_file_under_artifacts_is_rejected(self):
        put(self.base / "private/settings.json", {"secret": "DO_NOT_PACKAGE"})
        with self.assertRaises(ValueError):
            self.export()

    def test_archive_byte_damage_is_rejected(self):
        self.export()
        archive_path = self.output / "evidence.zip"
        raw = archive_path.read_bytes()
        archive_path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        with self.assertRaises(ValueError):
            exporter.verify(self.output / "manifest.json")

    def test_member_byte_damage_is_rejected_after_updating_outer_archive_hash(self):
        self.export()
        members = self.archive_members()
        members[ARTIFACT + "/mapping.json"] += b" "
        self.rewrite(list(members.items()))
        with self.assertRaises(ValueError):
            exporter.verify(self.output / "manifest.json")

    def test_unsafe_archive_member_is_rejected_even_when_manifest_hashes_match(self):
        self.export()
        members = list(self.archive_members().items()) + [("../escape.json", b"{}\n")]
        def change(manifest):
            manifest["payload"]["files"].append({"path": "../escape.json", "bytes": 3, "sha256": sha(b"{}\n")})
        self.rewrite(members, manifest_changes=change)
        with self.assertRaises(ValueError):
            exporter.verify(self.output / "manifest.json")

    def test_duplicate_archive_member_is_rejected(self):
        self.export()
        members = list(self.archive_members().items())
        self.rewrite(members + [members[0]])
        with self.assertRaises(ValueError):
            exporter.verify(self.output / "manifest.json")

    def test_protocol_binding_is_checked_independently_of_member_hashes(self):
        self.export()
        members = self.archive_members()
        changed = encoded({**self.protocol, "protocol_id": "tampered-protocol"})
        members[PROTOCOL] = changed
        def change(manifest):
            entry = next(row for row in manifest["payload"]["files"] if row["path"] == PROTOCOL)
            entry.update(bytes=len(changed), sha256=sha(changed))
        self.rewrite(list(members.items()), manifest_changes=change)
        with self.assertRaises(ValueError):
            exporter.verify(self.output / "manifest.json")

    def test_unsafe_archive_reference_is_rejected(self):
        self.export()
        manifest = read(self.output / "manifest.json")
        manifest["archive"]["path"] = "../evidence.zip"
        put(self.output / "manifest.json", manifest)
        with self.assertRaises(ValueError):
            exporter.verify(self.output / "manifest.json")

    def test_compat_export_binds_active_protocol_and_preserves_both_conditions(self):
        base, _protocol, digest = self.compat_fixture()
        # The original condition contributes only its two failed probes.
        original_cells = []
        for index in range(2):
            call_id = str(index + 1) * 64
            original_cells.append({"model": f"fixture-model-{index}", "condition": "schema_probe",
                                   "item_id": "synthetic-probe", "technical_status": "invalid",
                                   "vote": None, "call_id": call_id})
            put(self.base / "raw" / call_id / "request.json", {"model": f"fixture-model-{index}"})
        put(self.base / "new-annotations.json", {"protocol_sha256": self.protocol_digest, "cells": original_cells})
        active_cells = [{"model": "fixture-model", "condition": "full_context", "item_id": "synthetic-study",
                         "technical_status": "invalid", "vote": None, "call_id": "d" * 64}]
        put(base / "new-annotations.json", {"protocol_sha256": digest, "cells": active_cells})
        put(base / "raw" / ("d" * 64) / "request.json", {"model": "fixture-model"})
        manifest = self.export(condition="compat")
        payload = manifest["payload"]
        self.assertEqual(payload["condition"], "compat")
        self.assertEqual(payload["protocol_path"], COMPAT_PROTOCOL)
        self.assertEqual(payload["protocol_sha256"], digest)
        self.assertEqual(payload["planned_calls"], 192)
        self.assertEqual(payload["authorized_total_calls"], 194)
        self.assertEqual(payload["annotation_state"], "measured")
        self.assertEqual(payload["study_attempted_cells"], 1)
        self.assertEqual(payload["total_attempted_cells_including_parent"], 3)
        parent = payload["parent_condition_state"]
        self.assertEqual(parent["attempted_cells"], 2)
        self.assertEqual(parent["schema_probe_attempted_cells"], 2)
        self.assertEqual(parent["study_attempted_cells"], 0)
        self.assertEqual(parent["annotation_state"], "no_new_annotations")
        members = self.archive_members()
        for name in (PROTOCOL, COMPAT_PROTOCOL, ARTIFACT + "/input-items.json", COMPAT_ARTIFACT + "/input-items.json",
                     ARTIFACT + "/source-snapshot.zip", ARTIFACT + "/new-annotations.json",
                     COMPAT_ARTIFACT + "/new-annotations.json", "cross_model_compat.py"):
            self.assertIn(name, members)
        self.assertEqual(exporter.verify(self.output / "manifest.json")["status"], "passed")

    def test_compat_export_rejects_wrong_parent_protocol_link(self):
        _base, protocol, _digest = self.compat_fixture()
        protocol["parent_protocol_sha256"] = "0" * 64
        put(self.project / COMPAT_PROTOCOL, protocol)
        with self.assertRaises(ValueError):
            self.export(condition="compat")

    def test_compat_export_requires_original_artifact_inputs(self):
        self.compat_fixture()
        (self.base / "mapping.json").unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.export(condition="compat")

    def test_compat_annotations_cannot_bind_to_original_protocol(self):
        base, _protocol, _digest = self.compat_fixture()
        put(base / "new-annotations.json", {"protocol_sha256": self.protocol_digest, "cells": []})
        with self.assertRaises(ValueError):
            self.export(condition="compat")


if __name__ == "__main__":
    unittest.main()
