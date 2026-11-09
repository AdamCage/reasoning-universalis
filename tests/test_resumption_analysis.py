"""Scientific guards for fixed-prefix, source-only transfer evaluation."""

import hashlib
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from resumption.analysis import (FeatureSpace, chunk_spans, geometry, paired_gain,
                                 matched_prefixes, prefixes, read_records, run_analysis,
                                 transfer_fold, validate_records)


def observation(model="source-a", root="train-0", split="train", correct=True, suffix=""):
    # Each chunk has content, while ordering retains a small nontrivial trajectory.
    blocks = [" ".join([word] * 12 + ["calculate", "value", str(index), "carefully"])
              for index, word in enumerate(("start", "choose", "derive", "check", "derive", "verify", "revisit", "finish"))]
    return {"trace_id": f"{model}:{root}", "root_id": root, "model": model,
            "split": split, "domain": "logic", "difficulty": "hard", "correct": correct,
            "status": "completed", "text": " ".join(blocks) + suffix}


def embedding_observation(row, embedder):
    result = copy.deepcopy(row)
    dimension = 1024 if embedder == "baai/bge-m3" else 3
    result["embeddings"] = {embedder: [
        {**chunk, "vector": [1.] + [0.] * (dimension - 1),
         "model_id": embedder, "identity_verified": True,
         "input_sha256": hashlib.sha256(chunk["text"].encode()).hexdigest()}
        for chunk in chunk_spans(row["text"], 128)]}
    return result


class PrefixAndLeakageTests(unittest.TestCase):
    def test_invalid_prefix_budget_is_not_mislabeled_short_trace_coverage(self):
        with self.assertRaisesRegex(ValueError, "positive multiple"):
            prefixes([observation()], 1)
        with self.assertRaisesRegex(ValueError, "four complete chunks"):
            run_analysis([observation()], (32,), bootstrap_samples=0)

    def test_future_suffix_cannot_change_any_observed_prefix_feature(self):
        first = observation()
        second = observation(suffix=" future_secret " * 400)
        left = prefixes([first], 128)[0][0]
        right = prefixes([second], 128)[0][0]
        self.assertEqual(left.text, right.text)
        self.assertEqual(left.chunks, right.chunks)
        space = FeatureSpace("lexical").fit([left])
        np.testing.assert_allclose(space.transform([left], "dynamic").toarray(),
                                   space.transform([right], "dynamic").toarray())

    def test_cross_split_duplicates_are_rejected_even_across_models(self):
        rows = [observation(), observation("target", split="test")]
        with self.assertRaisesRegex(ValueError, "root crosses"):
            validate_records(rows)

    def test_target_vocabulary_never_enters_fit(self):
        train = prefixes([observation()], 128)[0]
        space = FeatureSpace("lexical").fit(train)
        target = observation("target", "test-0", "test")
        target["text"] = "target_secret " * 128
        target_prefix = prefixes([target], 128)[0]
        space.transform(target_prefix, "dynamic")
        self.assertNotIn("target_secret", space.vectorizer.vocabulary_)
        self.assertNotIn("target", space.manifest()["training_models"])
        self.assertEqual(space.manifest()["training_roots"], ["train-0"])

    def test_short_traces_are_excluded_with_disclosed_coverage(self):
        row = observation()
        row["text"] = "too short"
        selected, coverage = prefixes([row], 128)
        self.assertEqual(selected, [])
        self.assertEqual(sum(c.get("shorter_than_budget", 0) for c in coverage.values()), 1)

    def test_exact_embedding_identity_and_input_required(self):
        row = observation()
        segments = []
        for chunk in chunk_spans(row["text"], 128):
            segments.append({**chunk, "vector": [1.0] + [0.0] * 1023,
                             "model_id": "baai/bge-m3", "identity_verified": True,
                             "input_sha256": hashlib.sha256(chunk["text"].encode()).hexdigest()})
        row["embeddings"] = {"baai/bge-m3": segments}
        self.assertEqual(len(prefixes([row], 128, "baai/bge-m3")[0]), 1)
        segments[0]["text"] += " future"
        eligible, coverage = prefixes([row], 128, "baai/bge-m3")
        self.assertFalse(eligible)
        self.assertTrue(any("embedding_excluded:" in key for c in coverage.values() for key in c))

    def test_final_answer_marker_rejected(self):
        row = observation(suffix=" ANSWER: SAT")
        with self.assertRaisesRegex(ValueError, "answer marker"):
            prefixes([row], 128)

    def test_failed_attempts_with_unknown_outcomes_remain_in_coverage(self):
        row = observation()
        row.update(status="transport_failed", text="", correct=None)
        selected, coverage = prefixes([row], 128)
        self.assertEqual(selected, [])
        self.assertEqual(sum(c.get("not_completed", 0) for c in coverage.values()), 1)
        self.assertEqual(sum(c.get("attempted_records", 0) for c in coverage.values()), 1)

    def test_completed_attempt_with_unknown_outcome_is_rejected(self):
        row = observation()
        row["correct"] = None
        with self.assertRaisesRegex(ValueError, "independently verified Boolean"):
            prefixes([row], 128)

    def test_explicitly_ungradeable_completed_trace_remains_in_coverage(self):
        row = observation()
        row.update(correct=None, gradable=False)
        selected, coverage = prefixes([row], 128)
        self.assertFalse(selected)
        self.assertEqual(sum(c.get("grading_unavailable", 0) for c in coverage.values()), 1)

    def test_runner_json_array_and_jsonl_read_same_records(self):
        rows = [observation(), observation("source-b")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            for value in (rows, {"phase": "collection", "records": rows}):
                path.write_text(json.dumps(value))
                self.assertEqual(read_records(path), rows)
            path.write_text("\n".join(json.dumps(row) for row in rows))
            self.assertEqual(read_records(path), rows)
            path.write_text(json.dumps(rows[0]))
            self.assertEqual(read_records(path), rows[:1])

    def test_admission_cannot_silently_become_scientific_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            path.write_text(json.dumps({"phase": "admission", "records": [observation()]}))
            with self.assertRaisesRegex(ValueError, "smoke-only"):
                read_records(path)
            self.assertEqual(read_records(path, allow_admission_smoke=True), [observation()])


class GeometryAndTransferTests(unittest.TestCase):
    def test_oov_chunk_diagnostics_do_not_change_eligible_rows(self):
        train = prefixes([observation()], 128)[0]
        space = FeatureSpace("lexical").fit(train)
        target = observation("target", "test-0", "test")
        target["text"] = "unobservedtargetonly " * 128
        selected = prefixes([target], 128)[0]
        original = space.transform(selected, "dynamic").toarray()
        diagnostic = space.lexical_chunk_coverage(selected)
        self.assertEqual(diagnostic["chunks"], 8)
        self.assertEqual(diagnostic["zero_chunks"], 8)
        self.assertEqual(diagnostic["entirely_zero_traces"], 1)
        self.assertEqual(diagnostic["zero_chunk_fraction"], 1.)
        np.testing.assert_array_equal(original, space.transform(selected, "dynamic").toarray())

    def test_order_control_preserves_static_content_but_changes_geometry(self):
        rows = prefixes([observation(), observation("source-a", "train-1", correct=False)], 128)[0]
        observed = FeatureSpace("lexical", "observed").fit(rows)
        shuffled = FeatureSpace("lexical", "shuffle", 77).fit(rows)
        np.testing.assert_allclose(observed._numeric(rows, "static"), shuffled._numeric(rows, "static"))
        self.assertFalse(np.allclose(observed._numeric(rows, "dynamic"), shuffled._numeric(rows, "dynamic")))

    def test_identical_vectors_have_finite_zero_path_features(self):
        values = geometry(np.ones((8, 4)))
        self.assertTrue(np.all(np.isfinite(values)))
        self.assertAlmostEqual(values[0], 0)
        self.assertAlmostEqual(values[5], 0)

    def test_outer_fold_uses_only_sources_and_separate_roots(self):
        rows = []
        for model in ("source-a", "source-b", "target"):
            for split in ("train", "val", "test"):
                for index in range(2):
                    rows.append(observation(model, f"{split}-{index}", split, correct=index == 0))
        selected, _ = prefixes(rows, 128)
        fold = transfer_fold(selected, "target", "lexical")
        self.assertEqual(fold["status"], "evaluated")
        self.assertEqual(fold["feature_manifest"]["training_models"], ["source-a", "source-b"])
        self.assertEqual(fold["feature_manifest"]["training_roots"], ["train-0", "train-1"])
        self.assertEqual(fold["test_roots"], ["test-0", "test-1"])
        self.assertEqual(len(fold["predictions"]), 6)

    def test_single_training_class_is_reported_and_finite(self):
        rows = [observation("source-a", "train", "train", True),
                observation("source-b", "train", "train", True),
                observation("source-a", "val", "val", True),
                observation("target", "test", "test", False)]
        selected, _ = prefixes(rows, 128)
        fold = transfer_fold(selected, "target", "lexical")
        self.assertEqual(fold["methods"]["static"]["estimator"], "smoothed_constant_one_training_class")
        self.assertIsNone(fold["methods"]["static"]["test"]["auroc"])

    def test_equal_root_estimand_does_not_overweight_repeated_traces(self):
        predictions = []
        # Root a has 10 replicates, root b one. Their gains are equal/opposite.
        for root, repeats, reference, dynamic in (("a", 10, 0.5, 0.8), ("b", 1, 0.8, 0.5)):
            for index in range(repeats):
                for method, probability in (("static", reference), ("dynamic", dynamic)):
                    predictions.append({"trace_id": f"{root}:{index}", "root_id": root,
                                        "correct": True, "method": method, "probability": probability})
        result = paired_gain(predictions, bootstrap_samples=100)
        self.assertAlmostEqual(result["log_loss_gain"], 0.0)
        self.assertAlmostEqual(result["brier_gain"], 0.0)
        self.assertEqual(result["root_count"], 2)
        self.assertEqual(result["trace_count"], 11)
        self.assertLess(result["log_loss_gain_ci95"][0], 0)
        self.assertGreater(result["log_loss_gain_ci95"][1], 0)

    def test_unavailable_folds_cannot_be_mistaken_for_findings(self):
        result = run_analysis([observation()], (128,), bootstrap_samples=0, include_order_controls=False)
        self.assertEqual(result["E0"], "not_passed")
        self.assertEqual(result["runs"][0]["folds"][0]["status"], "unavailable")
        self.assertEqual(result["runs"][0]["paired_gain"]["status"], "unavailable")

    def test_direct_order_contrasts_compare_same_roots_and_observed_predictions(self):
        rows = []
        for model in ("source-a", "source-b", "target"):
            for split in ("train", "val", "test"):
                for index in range(2):
                    rows.append(observation(model, f"{split}-{index}", split, correct=index == 0))
        result = run_analysis(rows, (128,), bootstrap_samples=10)
        self.assertEqual(len(result["order_contrasts"]), 4)
        self.assertEqual({contrast["control_order"] for contrast in result["order_contrasts"]}, {"reverse", "shuffle"})
        for contrast in result["order_contrasts"]:
            self.assertEqual(contrast["paired_gain"]["root_count"], 2)
            self.assertEqual(contrast["paired_gain"]["trace_count"], 6)
            self.assertIn("not_adjusted", contrast["multiplicity"])
            self.assertEqual(len(contrast["paired_gain_by_target"]), 3)
            self.assertTrue(all(value["trace_count"] == 2 for value in contrast["paired_gain_by_target"].values()))
        self.assertEqual(len(result["runs"][0]["paired_gain_by_target"]), 3)


class MatchedEmbeddingTests(unittest.TestCase):
    def fixture(self):
        rows = []
        for model in ("source-a", "source-b", "target"):
            for split, count in (("train", 4), ("val", 2), ("test", 2)):
                rows.extend(observation(model, f"{split}-{index}", split, correct=bool(index % 2))
                            for index in range(count))
        bge = [embedding_observation(row, "baai/bge-m3") for row in rows]
        qwen = [embedding_observation(row, "qwen/qwen3-embedding-8b") for row in rows]
        # Remove companion coverage in every split. Matching only target
        # predictions would leave the excluded source roots in fitted models.
        for row in qwen:
            if row["root_id"] in {"train-3", "val-1", "test-1"}:
                row["embeddings"] = {}
        return bge, qwen

    def test_matching_is_symmetric_and_precedes_source_validation_and_target_fits(self):
        bge, qwen = self.fixture()
        bge_rows, _, details = matched_prefixes(bge, qwen, 128, "baai/bge-m3", "qwen/qwen3-embedding-8b")
        qwen_rows, _, reverse = matched_prefixes(qwen, bge, 128, "qwen/qwen3-embedding-8b", "baai/bge-m3")
        self.assertEqual({row.trace_id for row in bge_rows}, {row.trace_id for row in qwen_rows})
        self.assertEqual(details["matched_trace_ids"], reverse["matched_trace_ids"])
        self.assertEqual(details["primary_eligible"], 24)
        self.assertEqual(details["matched_eligible"], 15)
        self.assertEqual(len(details["primary_excluded_trace_ids"]), 9)
        result = run_analysis(bge, (128,), "baai/bge-m3", 10, False,
                              matched_records=qwen, matched_embedder="qwen/qwen3-embedding-8b")
        target = next(fold for fold in result["runs"][0]["folds"] if fold["target_model"] == "target")
        self.assertEqual(target["feature_manifest"]["training_roots"], ["train-0", "train-1", "train-2"])
        self.assertEqual(target["validation_roots"], ["val-0"])
        self.assertEqual(target["test_roots"], ["test-0"])
        self.assertEqual(result["analysis_population"], "supplementary_matched_embedding_prefixes")
        self.assertIn("primary_estimand_unchanged", details["scope"])
        self.assertEqual(result["runs"][0]["paired_gain"]["interval_status"],
                         "not_estimated_insufficient_independent_roots")

    def test_original_primary_analysis_keeps_its_own_coverage(self):
        bge, _ = self.fixture()
        result = run_analysis(bge, (128,), "baai/bge-m3", 0, False)
        self.assertEqual(result["runs"][0]["eligible_rows"], 24)
        self.assertIsNone(result["runs"][0]["matched_embedding_coverage"])
        self.assertEqual(result["analysis_population"], "original_embedder_specific_eligible_prefixes")

    def test_matching_rejects_same_trace_with_disagreeing_labels_or_text(self):
        bge, qwen = self.fixture()
        qwen[0]["correct"] = not qwen[0]["correct"]
        with self.assertRaisesRegex(ValueError, "disagree on trace identity"):
            matched_prefixes(bge, qwen, 128, "baai/bge-m3", "qwen/qwen3-embedding-8b")


if __name__ == "__main__":
    unittest.main()
