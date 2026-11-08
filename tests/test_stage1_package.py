"""Review-package integrity guards, not tests of scientific measurement validity."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stage1_verify", ROOT / "design/verify_stage1.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)
APPROVED_SNAPSHOT = "68fc12da05000674e3d770a07e449c37a4fbc119"
APPROVED_PAYLOAD_SHA256 = "04988a3ec82db073a04a71519e35f91740398d9a66636dc2935ce3377c079963"


class ReviewPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This is a historical approval fixture, not the evolving working tree.
        receipt = json.loads((ROOT / "design/G1.json").read_bytes())
        if (receipt["approved_commit"] != APPROVED_SNAPSHOT or
                receipt["approved_artifact_hashes"]["payload_sha256"] != APPROVED_PAYLOAD_SHA256):
            raise AssertionError("Stage 1 approval receipt differs from the pinned historical fixture")
        try:
            cls.snapshot = {path: subprocess.check_output(
                ["git", "-C", str(ROOT), "show", APPROVED_SNAPSHOT + ":" + path],
                stderr=subprocess.PIPE)
                for path in verify.REVIEW_FILES | {verify.MANIFEST}}
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("Stage 1 tests require the approved Git snapshot " + APPROVED_SNAPSHOT +
                               "; use a full Git clone/history, not a shallow or source-only archive") from exc

    def setUp(self):
        self.files = dict(self.snapshot)

    def read(self, path):
        return self.files[path]

    def rewrite(self, path, change):
        value = json.loads(self.files[path])
        change(value)
        data = verify.canonical(value)
        self.files[path] = data
        manifest = json.loads(self.files[verify.MANIFEST])
        row = next(row for row in manifest["payload"]["files"] if row["path"] == path)
        row.update(bytes=len(data), sha256_git_blob_bytes=verify.sha(data),
                   git_blob=hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest())
        manifest["payload_sha256"] = verify.sha(verify.canonical(manifest["payload"]))
        self.files[verify.MANIFEST] = verify.canonical(manifest)

    def test_review_ready_is_not_approval(self):
        result = verify.verify(self.read)
        self.assertEqual(result["G1"], "pending_in_review_snapshot")
        self.assertEqual(result["E0"], "not_passed")
        self.assertEqual(result["hypotheses"], 8)

    def test_byte_tampering_rejected(self):
        self.files["design/prompts/segment-role-v1.md"] += b"\nchanged"
        with self.assertRaisesRegex(ValueError, "File bytes mismatch"):
            verify.verify(self.read)

    def test_shortened_hypothesis_rejected_even_with_new_manifest(self):
        def shorten(data):
            h = data["hypotheses"][1]
            h["source_text"] = h["source_text"].split("\n\n")[0]
            h["source_text_sha256_lf"] = verify.sha(h["source_text"].encode())
        self.rewrite("design/hypotheses.json", shorten)
        with self.assertRaisesRegex(ValueError, "Hypothesis source altered"):
            verify.verify(self.read)

    def test_premature_final_threshold_rejected(self):
        self.rewrite("design/hypotheses.json", lambda data:
                     data["hypotheses"][1]["operational_fields"].update(minimally_meaningful_effect=0.1))
        with self.assertRaisesRegex(ValueError, "Final G2 fields filled prematurely"):
            verify.verify(self.read)

    def test_reused_seed_rejected(self):
        self.rewrite("design/ANNOTATION_CONFIG.json", lambda data:
                     data["seed_schedule"][1].__setitem__(0, data["seed_schedule"][0][0]))
        with self.assertRaisesRegex(ValueError, "Invalid seed schedule"):
            verify.verify(self.read)

    def test_historical_root_cannot_be_confirmatory(self):
        self.rewrite("design/historical-development-manifest.json", lambda data:
                     data["tasks"][0].update(split="confirmatory"))
        with self.assertRaisesRegex(ValueError, "Historical roots leaked"):
            verify.verify(self.read)


if __name__ == "__main__":
    unittest.main()
