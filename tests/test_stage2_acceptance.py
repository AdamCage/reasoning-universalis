"""Guards for the Stage 2 acceptance receipt. They do not measure E0."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "stage2_acceptance", ROOT / "design/verify_stage2_acceptance.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class Stage2AcceptanceTests(unittest.TestCase):
    def setUp(self):
        paths = [verify.MANIFEST, verify.RECEIPT, verify.NARRATIVE, verify.EVIDENCE, *verify.LOCKS]
        manifest = json.loads((ROOT / verify.MANIFEST).read_bytes())
        paths.extend(row["path"] for row in manifest["payload"]["files"])
        self.files = {path: (ROOT / path).read_bytes() for path in dict.fromkeys(paths)}

    def read(self, path):
        return self.files[path]

    def test_receipt_accepts_unchanged_payload_without_passing_e0(self):
        result = verify.verify(self.read)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["criteria"], 15)
        self.assertEqual(result["E0"], "not_passed")
        self.assertEqual(result["G2"], "not_frozen")
        self.assertEqual(result["scientific_validity"], "not_assessed")
        self.assertEqual(result["paid_stage2_calls"], 0)
        self.assertEqual(result["payload_sha256"], verify.PAYLOAD_SHA256)

    def test_changed_implementation_file_is_rejected(self):
        self.files["stage2/datasets.py"] += b"\n# changed after acceptance\n"
        with self.assertRaisesRegex(ValueError, "Implementation file changed"):
            verify.verify(self.read)

    def test_receipt_cannot_pass_e0_or_start_the_pilot(self):
        receipt = json.loads(self.files[verify.RECEIPT])
        receipt["E0"] = "passed"
        with self.assertRaisesRegex(ValueError, "cannot pass E0"):
            verify.check_receipt(receipt)
        receipt["E0"] = "not_passed"
        receipt["stage3_started"] = True
        with self.assertRaisesRegex(ValueError, "Pilot was started"):
            verify.check_receipt(receipt)
        receipt["stage3_started"] = False
        receipt["scientific_validity"] = "approved"
        with self.assertRaisesRegex(ValueError, "scientific validity"):
            verify.check_receipt(receipt)

    def test_rewritten_receipt_bytes_are_rejected(self):
        self.files[verify.RECEIPT] = self.files[verify.RECEIPT].replace(
            b'"paid_stage2_calls": 0', b'"paid_stage2_calls": 1')
        with self.assertRaisesRegex(ValueError, "cannot pass E0|includes a paid call|bytes mismatch"):
            verify.verify(self.read)
