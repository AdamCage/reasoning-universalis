"""Bind the Stage 2 acceptance receipt to the unchanged implementation payload.

Passing this check accepts the measurement pipeline under RESEARCH_PLAN §8.
It does not pass E0, freeze G2, or create a scientific claim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "reports/STAGE2_MANIFEST.json"
RECEIPT = "reports/STAGE2_ACCEPTANCE.json"
NARRATIVE = "reports/STAGE2_ACCEPTANCE.md"
EVIDENCE = "evidence/stage2-2026-10-14.zip"
PAYLOAD_SHA256 = "03932e8f90dd3a8fa1b7d22a42c1cd0527585e70a158a6f1fb6decba39e0dab8"
EVIDENCE_SHA256 = "74b0f24a80955af6475831532db83b62b79b671413aba3ca2b12d4686b4327fe"
RECEIPT_SHA256 = "47fcab3c254f1229f87abcb6fa777c2c72d73a5726eb5bd1d0b8e7dad547a287"
LOCKS = {
    "RESEARCH_SPECIFICATION.md": "a776fbd34d4a0a8172127debe71395f94c8586af187400200bfe847000dd26ee",
    "EpistemeOS/README.md": "073d75ec59d0ca34497fa09f2e11e89e5d24da954c7d5285e5749461a010a650",
    "EpistemeOS/AGENTS.md": "92010715ae0816302a2f2056e9aaf0cceb91290a1c47f4dd17e46765d3e7cd7b",
    "reports/MODEL_LICENSES.md": "c0f733b1395933858879e390786040c0781c306d69e137b2194f69ffe4d26847",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def check_receipt(receipt: dict) -> None:
    require(receipt.get("stage") == 2, "Wrong stage")
    require(receipt.get("status") == "accepted", "Stage 2 receipt is not accepted")
    require(receipt.get("E0") == "not_passed", "Stage 2 cannot pass E0")
    require(receipt.get("human_validation") == "deferred", "Human validation was deferred")
    require(receipt.get("G2") == "not_frozen", "Stage 2 cannot freeze G2")
    require(receipt.get("G3") == "not_completed" and receipt.get("G4") == "not_completed", "Later gates are not complete")
    require(receipt.get("scientific_validity") == "not_assessed", "Stage 2 cannot assess scientific validity")
    require(receipt.get("paid_stage2_calls") == 0, "Stage 2 acceptance includes a paid call")
    require(receipt.get("stage3_started") is False and receipt.get("pilot_section_5_5_started") is False, "Pilot was started inside Stage 2")
    require(receipt.get("implementation_payload_sha256") == PAYLOAD_SHA256, "Receipt points at another payload")
    require(receipt.get("evidence_sha256") == EVIDENCE_SHA256, "Receipt points at another evidence archive")
    require(receipt.get("nemotron_called") is False, "Nemotron call was not part of this stage")
    require(receipt.get("nemotron_license") == "NVIDIA Nemotron Open Model License", "Nemotron license was renamed")
    criteria = receipt.get("criteria_met")
    require(isinstance(criteria, dict) and set(criteria) == {str(i) for i in range(1, 16)}, "Criteria 1–15 are incomplete")
    require(all(isinstance(criteria[str(i)], str) and criteria[str(i)].strip() for i in range(1, 16)), "Empty criterion")
    models = receipt.get("live_models_on_stage2")
    require(isinstance(models, list) and len(models) == 1, "Stage 2 live-model list changed")
    model = models[0]
    require(model.get("model_id") == "openai/gpt-oss-20b" and model.get("license") == "Apache-2.0", "GPT-OSS license record changed")
    require(model.get("full_trace_obtained_at_harness_stage0") is True, "Stage 0 full-trace admission missing")
    require(model.get("new_live_call_on_stage2") is False, "New live generation recorded as Stage 2")
    locks = receipt.get("unchanged_locks")
    require(isinstance(locks, dict) and set(locks) == set(LOCKS), "Unchanged-file lock roster differs")
    for path, digest in LOCKS.items():
        require(locks[path].get("sha256") == digest, "Receipt lock digest differs: " + path)


def verify(read) -> dict:
    manifest = json.loads(read(MANIFEST))
    require(set(manifest) == {"payload", "payload_sha256"}, "Unexpected Stage 2 manifest fields")
    payload = manifest["payload"]
    require(sha(canonical(payload)) == manifest["payload_sha256"] == PAYLOAD_SHA256, "Implementation payload digest mismatch")
    require(payload.get("status") == "implementation_ready_for_review_not_E0", "Implementation payload was rewritten after review")
    require(payload.get("paid_stage2_calls") == 0 and payload.get("E0") == "not_passed", "Payload claims a paid call or passed E0")
    rows = payload["files"]
    require(len(rows) == len({row["path"] for row in rows}), "Duplicate payload path")
    for row in rows:
        data = read(row["path"])
        require(len(data) == row["bytes"] and sha(data) == row["sha256"], "Implementation file changed: " + row["path"])
    evidence = read(EVIDENCE)
    require(len(evidence) == 484814 and sha(evidence) == EVIDENCE_SHA256, "Evidence archive changed")
    for path, digest in LOCKS.items():
        require(sha(read(path)) == digest, "Locked file changed: " + path)
    receipt_bytes = read(RECEIPT)
    require(sha(receipt_bytes) == RECEIPT_SHA256, "Acceptance receipt bytes mismatch")
    check_receipt(json.loads(receipt_bytes))
    narrative = read(NARRATIVE).decode()
    require(RECEIPT_SHA256 in narrative, "Acceptance narrative missing receipt digest")
    require("не пройден" in narrative and "NVIDIA Nemotron Open Model License" in narrative, "Acceptance narrative drops a required boundary")
    return {
        "stage": 2,
        "status": "accepted",
        "payload_sha256": PAYLOAD_SHA256,
        "evidence_sha256": EVIDENCE_SHA256,
        "receipt_sha256": RECEIPT_SHA256,
        "criteria": 15,
        "E0": "not_passed",
        "G2": "not_frozen",
        "scientific_validity": "not_assessed",
        "paid_stage2_calls": 0,
    }


def main() -> None:
    def read(path: str) -> bytes:
        return (ROOT / path).read_bytes()

    print(json.dumps(verify(read), indent=2))


if __name__ == "__main__":
    main()
