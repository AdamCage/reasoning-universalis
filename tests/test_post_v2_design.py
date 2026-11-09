"""Selection/censoring/paired-root checks; closed artifacts are read-only."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_post_v2_design import analyze, build, lengths, outcome, quantiles, validate_inputs

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    tasks, records = [], []
    for root in range(2):
        for variant in range(2):
            task = {"task_id": f"r{root}v{variant}", "root_id": f"r{root}", "domain": "logic", "tier": "low",
                    "reference_certificate": {"kind": "exhaustive_cnf_truth_table", "answer": "SAT"}}
            tasks.append(task)
            for cap in (2048, 8192):
                records.append({**task, "model": "a", "provider": "fixture", "output_budget_tokens": cap,
                    "trace_id": f"{task['task_id']}:{cap}", "seed": root * 2 + variant, "sample_index": 0,
                    "raw_reasoning_text": "reason " * 512, "text": "reason " * 512, "correct": True, "gradable": True,
                    "status": "completed", "finish_reason": "stop", "attempted": True, "http_status": 200,
                    "request_state": "finished", "identity_verified": True, "provider_route_verified": True,
                    "observed_trace_status": "visible_trace_candidate", "protocol_sha256": "fixture"})
    return tasks, records


def real_paths():
    return {
        "tasks": ROOT / "artifacts/pilot-v2-2026-11-08/development-tasks.json",
        "a-protocol": ROOT / "design/PILOT_V2_PROTOCOL_2026_11_08.json",
        "a-results": ROOT / "artifacts/pilot-v2-2026-11-08/results.json",
        "r1-protocol": ROOT / "design/PILOT_V2_PROVIDER_RECOVERY_PROTOCOL.json",
        "r1-results": ROOT / "artifacts/pilot-v2-recovery-2026-11-08/results.json",
        "r1-support": ROOT / "artifacts/pilot-v2-recovery-2026-11-08/class-support.json",
        "source-inventory": ROOT / "artifacts/pilot-v2-recovery-2026-11-08/source-inventory.json",
    }


class PostV2SelectionTests(unittest.TestCase):
    def test_unicode_crlf_first_answer_censor_never_borrows_later_words(self):
        tasks, records = fixture()
        record = records[0]
        record.update(raw_reasoning_text="α\r\nβ ANSWER: " + "hidden " * 600, text="α\r\nβ ", correct=False)
        count = lengths(record)
        self.assertEqual(count["answer_marker_character"], 5)
        self.assertEqual(count["prefix_before_answer_words"], 2)
        self.assertEqual(count["suffix_after_answer_words"], 600)
        result = analyze(records, tasks, ["a"])
        error = result["completed_errors"][0]
        self.assertGreater(error["raw_reasoning_words"], 512)
        self.assertFalse(error["eligible_128"])
        self.assertFalse(error["eligible_256"])
        group = next(row for row in result["grouped_support"] if row["scope"] == "all"
                     and row["output_budget_tokens"] == 2048 and row["prefix_words"] == 256)
        self.assertEqual(group["completed_raw_below_prefix"], 0)
        self.assertEqual(group["completed_raw_long_but_preanswer_short"], 1)

    def test_censored_null_is_not_an_error_even_with_long_returned_reasoning(self):
        _, records = fixture()
        record = records[0]
        record.update(status="truncated", finish_reason="length", budget_censored=True,
                      correct=None, gradable=False, raw_answer_grading={"verdict": "incorrect"})
        self.assertEqual(outcome(record), "censored")
        record["correct"] = False
        with self.assertRaisesRegex(ValueError, "must remain null"):
            outcome(record)

    def test_two_variant_completion_gains_remain_one_root_block(self):
        tasks, records = fixture()
        for record in records:
            if record["root_id"] == "r0" and record["output_budget_tokens"] == 2048:
                record.update(status="truncated", finish_reason="length", correct=None, gradable=False)
        result = analyze(records, tasks, ["a"])
        summary = next(row for row in result["paired_cap_summary"] if row["scope"] == "all")
        self.assertEqual((summary["planned_task_pairs"], summary["independent_root_blocks"]), (4, 2))
        self.assertEqual(summary["completion_gained_pairs"], 2)
        self.assertEqual(summary["roots_with_net_completion_gain"], 1)
        self.assertEqual(sorted(row["net_completed_variant_delta"] for row in result["paired_cap_roots"]), [0, 2])

    def test_duplicate_matrix_or_changed_paired_seed_is_rejected(self):
        tasks, records = fixture()
        with self.assertRaisesRegex(ValueError, "exactly once"):
            analyze(records + [records[0]], tasks, ["a"])
        records[1]["seed"] += 1
        with self.assertRaisesRegex(ValueError, "sampling seed"):
            analyze(records, tasks, ["a"])

    def test_missing_reasoning_has_no_invented_zero_length_distribution(self):
        self.assertIsNone(lengths({"text": ""})["raw_reasoning_words"])
        self.assertFalse(lengths({"text": ""})["reasoning_present"])
        self.assertEqual(quantiles([])["n"], 0)
        self.assertIsNone(quantiles([])["median"])

    def test_real_closed_inputs_replay_deterministically_and_do_not_change(self):
        paths = real_paths()
        before = {name: path.read_bytes() for name, path in paths.items()}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = build(paths, root / "one/out", root / "one/report.md")
            second = build(paths, root / "two/out", root / "two/report.md")
            self.assertEqual(first, second)
            self.assertEqual({path.name: path.read_bytes() for path in (root / "one/out").iterdir()},
                             {path.name: path.read_bytes() for path in (root / "two/out").iterdir()})
            self.assertEqual((root / "one/report.md").read_bytes(), (root / "two/report.md").read_bytes())
            self.assertEqual(first["unique_sent_physical_calls_A_union_R1"], 194)
            self.assertEqual(len(first["R1"]["attempts"]), 192)
            self.assertEqual(len(first["R1"]["paired_cap_roots"]), 48)
            self.assertEqual(len(first["R1"]["completed_errors"]), 4)
            with self.assertRaisesRegex(ValueError, "explicitly replace owned"):
                build(paths, root / "one/out", root / "one/report.md")
            owned_before = {path.name: path.read_bytes() for path in (root / "one/out").iterdir()}
            build(paths, root / "one/out", root / "one/report.md", overwrite_owned=True)
            self.assertEqual(owned_before, {path.name: path.read_bytes() for path in (root / "one/out").iterdir()})
            (root / "one/out/attempt-matrix.csv").write_text("user edit", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "have been edited"):
                build(paths, root / "one/out", root / "one/report.md", overwrite_owned=True)
        self.assertEqual(before, {name: path.read_bytes() for name, path in paths.items()})

    def test_changed_reused_label_is_rejected_before_any_new_output(self):
        raw = {name: path.read_bytes() for name, path in real_paths().items()}
        docs = {name: json.loads(value) for name, value in raw.items()}
        next(row for row in docs["r1-results"]["records"] if row["model"].startswith("deepseek"))["correct"] = False
        with self.assertRaisesRegex(ValueError, "original DeepSeek"):
            validate_inputs(docs, raw)


if __name__ == "__main__":
    unittest.main()
