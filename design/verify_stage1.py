"""Read-only integrity checks for the Stage 1 review package; no scientific approval."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "design/STAGE1_APPROVAL_MANIFEST.json"
DEFERRED = "не задано спецификацией; решение отложено до заморозки протокола"
FIELDS = {
    "primary_metric", "direction", "null_model", "effect_size", "confidence_interval",
    "significance_plan", "multiple_testing_family", "minimally_meaningful_effect",
    "insufficient_power_criterion",
}
REVIEW_FILES = {
    "AGENTS.md", "STAGE1_CLOUD_HANDOFF.md", "RESEARCH_SPECIFICATION.md", "RESEARCH_PLAN.md",
    "design/SELECTED_DECISIONS.json", "design/STAGE1_PREPARATION_MANIFEST.json",
    "design/PREREGISTRATION_DRAFT.md", "design/hypotheses.json", "design/STATE_DISCOVERY.md",
    "design/ANNOTATION_PROTOCOL.md", "design/MACHINE_ANNOTATION_PROTOCOL.md",
    "design/ANNOTATION_CONFIG.json", "design/ANNOTATION_RESPONSE.schema.json",
    "design/prompts/segment-role-v1.md", "design/prompts/cluster-role-v1.md",
    "design/SPLITS.md", "design/E0_PRELIMINARY.json", "design/PILOT_COHORT_ADMISSION.md",
    "design/historical-development-manifest.json", "design/DOMAIN_PACK_DESIGN.md",
    "design/G1_APPROVAL.md", "design/verify_stage1.py", "reports/STAGE1_REPORT.md",
    "reports/PRE_PILOT_REVIEW_RESPONSE.md", "reports/MEASUREMENT_DEVELOPMENT.md",
    "literature/transfer-and-stopping-addendum.md",
    "tests/test_stage1_package.py",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Non-finite JSON: {value}")

    value = json.loads(data, object_pairs_hook=unique, parse_constant=invalid)
    require(type(value) is dict, "Expected JSON object")
    canonical(value)  # Also rejects overflowing floating-point literals.
    return value


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def verify(read) -> dict:
    manifest = strict_json(read(MANIFEST))
    require(set(manifest) == {"payload", "payload_sha256"}, "Unexpected manifest fields")
    payload = manifest["payload"]
    require(sha(canonical(payload)) == manifest["payload_sha256"], "Payload digest mismatch")
    require(payload["status"] == "review_ready_G1_pending_not_G2", "Not a review snapshot")
    require(payload["approver"] == "AdamCage", "Wrong designated approver")
    rows = payload["files"]
    paths = [row["path"] for row in rows]
    require(paths == sorted(REVIEW_FILES), "Missing, duplicate or unexpected review files")
    for row in rows:
        path = row["path"]
        require(not PurePosixPath(path).is_absolute() and ".." not in PurePosixPath(path).parts,
                "Unsafe manifest path")
        data = read(path)
        require(len(data) == row["bytes"] and sha(data) == row["sha256_git_blob_bytes"],
                f"File bytes mismatch: {path}")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(blob == row["git_blob"], f"Git blob mismatch: {path}")

    spec_bytes = read("RESEARCH_SPECIFICATION.md")
    source = spec_bytes.decode("utf-8").replace("\r\n", "\n")
    hypotheses = strict_json(read("design/hypotheses.json"))
    require(sha(source.encode()) == hypotheses["source_sha256_lf"] ==
            "a776fbd34d4a0a8172127debe71395f94c8586af187400200bfe847000dd26ee",
            "Specification changed")
    require(hypotheses["source_git_blob"] == "a9db63e35b389004e0cb5a62ea740dc999927907",
            "Wrong source Git blob")
    items = hypotheses["hypotheses"]
    require([item["id"] for item in items] == [f"H{i}" for i in range(8)],
            "Hypotheses incomplete or reordered")
    prereg = read("design/PREREGISTRATION_DRAFT.md").decode("utf-8")
    for item in items:
        text = item["source_text"]
        section = re.search(r"^## " + item["id"] + r"\. .*?(?=^## H[0-7]\.|^# 4\.)",
                            source, re.S | re.M)
        require(section is not None and section.group(0).strip() == text and text in prereg,
                f"Hypothesis source altered or absent: {item['id']}")
        require(sha(text.encode()) == item["source_text_sha256_lf"], "Hypothesis quote hash mismatch")
        require(set(item["operational_fields"]) == FIELDS and
                all(value == DEFERRED for value in item["operational_fields"].values()),
                f"Final G2 fields filled prematurely: {item['id']}")
        require(set(item["design_choices"]) == FIELDS and
                all(type(value) is str and value.strip() for value in item["design_choices"].values()),
                "Design candidates incomplete")
        require(all(item[key] for key in ("observable_signals", "allowed_conclusions",
                                          "forbidden_conclusions", "analysis_status",
                                          "support_source", "refutation_source")),
                "Operational hypothesis block incomplete")
        if item["id"] != "H0":
            for key in ("support_source", "refutation_source"):
                require(item[key] in text, "Support/refutation no longer matches original")

    selected = strict_json(read("design/SELECTED_DECISIONS.json"))
    require(selected["priority_and_measurement"]["article_scope"] == "B_all_H1_H7",
            "Article scope changed")
    config = strict_json(read("design/ANNOTATION_CONFIG.json"))
    require(config["model"] == "deepseek/deepseek-v4.1-flash" and
            (config["panel_size"], config["majority_required"], config["maximum_rounds"],
             config["automatic_retries"]) == (5, 3, 2, 0), "Annotation rule drift")
    seeds = config["seed_schedule"]
    require(len(seeds) == 2 and all(len(row) == 5 for row in seeds) and
            all(type(seed) is int for row in seeds for seed in row) and
            len({seed for row in seeds for seed in row}) == 10, "Invalid seed schedule")
    schema = strict_json(read(config["response_schema"]))
    require(schema["additionalProperties"] is False and
            schema["properties"]["primary_role"]["enum"] == config["roles"],
            "Annotation schema/config drift")
    for prompt in (config["segment_prompt"], config["cluster_prompt"]):
        require(prompt in REVIEW_FILES and b"```text" in read(prompt), "Prompt template missing")
    splits = strict_json(read("design/historical-development-manifest.json"))
    require(len(splits["tasks"]) == 6 and
            all(row["split"] == "development" for row in splits["tasks"]),
            "Historical roots leaked to holdout")
    e0 = strict_json(read("design/E0_PRELIMINARY.json"))
    require(e0["current_reference_status"] ==
            "human_validation_deferred_machine_ensemble_only_E0_not_passed", "False E0 claim")
    require(payload["research_question_source"] == "design/PREREGISTRATION_DRAFT.md" and
            payload["hypothesis_ontology_source"] == "design/hypotheses.json", "Wrong G1 scope")
    return {"status": "integrity_verified_not_scientific_approval", "files": len(rows),
            "hypotheses": len(items), "payload_sha256": manifest["payload_sha256"],
            "G1": "pending_in_review_snapshot", "E0": "not_passed", "network_calls": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", help="Verify exact repository blobs at this review commit")
    args = parser.parse_args()
    try:
        if args.commit:
            commit = git("rev-parse", "--verify", "--end-of-options", args.commit + "^{commit}").decode().strip()
            read = lambda path: git("show", commit + ":" + path)
        else:
            read = lambda path: (ROOT / path).read_bytes()
        print(json.dumps(verify(read), ensure_ascii=False, indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Stage 1 verification failed: {exc}\n")


if __name__ == "__main__":
    main()
