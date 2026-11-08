"""Fail-closed capture checks; fixtures do not represent scientific evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "EpistemeOS" / "src"))
from resumption_evidence_v1 import inventory


def fixture():
    files = {}; rows = []
    for role in ("protocol", "tasks", "results", "source"):
        name = role + ".json"; data = inventory.canonical({"synthetic_fixture": True, "role": role})
        files[name] = data
        rows.append({"path": name, "role": role, "format": "json", "sha256": inventory.sha(data), "bytes": len(data)})
    manifest = {"schema_version": 1, "purpose": "resumption_artifact_integrity_only",
        "scientific_validity": "not_assessed", "inference_mode": "exploratory", "artifacts": rows}
    files["manifest.json"] = inventory.canonical(manifest)
    return files, manifest


class EvidenceIntegrityTests(unittest.TestCase):
    def test_missing_file_and_missing_required_role_fail(self):
        files, manifest = fixture()
        del files["results.json"]
        with self.assertRaisesRegex(ValueError, "roster differs"):
            inventory.verify(files)
        files, manifest = fixture()
        del files["results.json"]
        manifest["artifacts"] = [r for r in manifest["artifacts"] if r["role"] != "results"]
        files["manifest.json"] = inventory.canonical(manifest)
        with self.assertRaisesRegex(ValueError, "Missing required"):
            inventory.verify(files)

    def test_tampered_bytes_and_invalid_json_fail(self):
        files, manifest = fixture()
        files["results.json"] += b" "
        with self.assertRaisesRegex(ValueError, "Captured bytes changed"):
            inventory.verify(files)
        files, manifest = fixture()
        files["results.json"] = b"invalid JSON"
        row = next(r for r in manifest["artifacts"] if r["role"] == "results")
        row.update(sha256=inventory.sha(files["results.json"]), bytes=len(files["results.json"]))
        files["manifest.json"] = inventory.canonical(manifest)
        with self.assertRaises(ValueError):
            inventory.verify(files)

    def test_scientific_success_cannot_be_declared_by_manifest(self):
        files, manifest = fixture()
        manifest["scientific_validity"] = "approved"
        files["manifest.json"] = inventory.canonical(manifest)
        with self.assertRaisesRegex(ValueError, "Wrong evidence manifest/status"):
            inventory.verify(files)

    def test_raw_reanalysis_is_bound_to_original_bytes(self):
        files, manifest = fixture()
        checked = inventory.verify(files)
        data = inventory.compiled(checked, files)
        raw = inventory.expected_raw(data, 0)
        self.assertEqual(inventory.metric(raw), len(files["protocol.json"]))
        changed = copy.deepcopy(raw); changed["artifact"]["base64"] = "e30="
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            inventory.metric(changed)

    def test_duplicate_role_path_and_unsafe_path_fail(self):
        files, manifest = fixture()
        manifest["artifacts"].append(dict(manifest["artifacts"][0]))
        files["manifest.json"] = inventory.canonical(manifest)
        with self.assertRaisesRegex(ValueError, "duplicate required role"):
            inventory.verify(files)
        files, manifest = fixture()
        manifest["artifacts"][0]["path"] = "../protocol.json"
        files["../protocol.json"] = files.pop("protocol.json")
        files["manifest.json"] = inventory.canonical(manifest)
        with self.assertRaisesRegex(ValueError, "Unsafe artifact path"):
            inventory.verify(files)


if __name__ == "__main__":
    unittest.main()
