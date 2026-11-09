"""Independent scientific invariants for prefix-transfer inference.

These tests use known probability/label fixtures rather than a fitted model's
reported significance. They guard against pseudoreplication, target leakage,
and inadvertent changes to the order-control estimand.
"""
from dataclasses import replace
import math
import unittest
from unittest.mock import patch

import numpy as np

from resumption.analysis import (
    FeatureSpace, Prefix, paired_gain, prefixes, transfer_fold, validate_records,
)


def prediction(trace, root, method, probability, *, label=True, model="target"):
    return {"trace_id": trace, "root_id": root, "model": model,
            "domain": "logic", "difficulty": "medium", "correct": label,
            "method": method, "probability": probability}


def paired(trace, root, reference, candidate, **kwargs):
    return [prediction(trace, root, "static", reference, **kwargs),
            prediction(trace, root, "dynamic", candidate, **kwargs)]


def row(trace, root, model, split, label):
    # Four unequal chunks produce nontrivial order statistics. The final two
    # words deliberately belong only to the held-out model/roots.
    suffix = " targetonly withheld" if model == "heldout" else " sourceonly known"
    chunks = (
        "begin count nodes and inspect the graph",
        "compare each directed edge with the proposed order",
        "check the local constraints once more before proceeding",
        "the graph ordering is internally consistent" + suffix,
    )
    text = " ".join(chunks)
    return Prefix(trace, root, model, split, "logic", "medium", label, text,
                  chunks, tuple((0, len(chunk)) for chunk in chunks),
                  np.array([[1., 0., 0.], [.8, .2, 0.], [0., .3, .7], [0., 0., 1.]]))


def transfer_fixture():
    rows = []
    for model in ("source-a", "source-b", "heldout"):
        for split, count in (("train", 4), ("val", 2), ("test", 3)):
            for index in range(count):
                rows.append(row(f"{model}-{split}-{index}", f"{split}-root-{index}",
                                model, split, bool(index % 2)))
    return rows


class EqualRootInferenceTests(unittest.TestCase):
    def test_one_original_root_has_a_point_estimate_but_no_uncertainty_interval(self):
        predictions = []
        for repeat in range(8):
            predictions += paired(f"repeat-{repeat}", "only-original-root", .5, .9,
                                  model=f"model-{repeat % 2}")
        observed = paired_gain(predictions, bootstrap_samples=200)
        self.assertAlmostEqual(observed["log_loss_gain"], math.log(.9 / .5))
        self.assertEqual(observed["root_count"], 1)
        self.assertEqual(observed["trace_count"], 8)
        self.assertEqual(observed["status"], "estimated")
        self.assertEqual(observed["interval_status"], "not_estimated_insufficient_independent_roots")
        self.assertIsNone(observed["log_loss_gain_ci95"])
        self.assertIsNone(observed["brier_gain_ci95"])
        self.assertIn("between-root uncertainty", observed["interval_limitation"])

    def test_invalid_bootstrap_configuration_is_not_an_empty_scientific_result(self):
        with self.assertRaisesRegex(ValueError, "nonnegative integer"):
            paired_gain(paired("a", "root-a", .5, .9), bootstrap_samples=-1)

    def test_unequal_repeats_and_models_do_not_change_root_estimand(self):
        predictions = paired("a", "root-a", .5, .9)
        for repeat in range(13):
            predictions += paired(f"b-{repeat}", "root-b", .5, .25,
                                  model=f"model-{repeat % 3}")
        observed = paired_gain(predictions, bootstrap_samples=0)
        gain_a, gain_b = math.log(.9 / .5), math.log(.25 / .5)
        self.assertAlmostEqual(observed["log_loss_gain"], (gain_a + gain_b) / 2)
        self.assertAlmostEqual(observed["brier_gain"], ((.25 - .01) + (.25 - .5625)) / 2)
        self.assertEqual(observed["root_count"], 2)
        self.assertEqual(observed["trace_count"], 14)
        # Treating 14 generations as independent would produce a different
        # point estimate; this fixture intentionally makes that mistake visible.
        self.assertNotAlmostEqual(observed["log_loss_gain"], (gain_a + 13 * gain_b) / 14)

    def test_duplicate_resampled_root_keeps_multiplicity(self):
        predictions = (paired("a", "a", .5, .9) + paired("b", "b", .5, .25)
                       + paired("c", "c", .5, .5))

        class FixedDraw:
            def integers(self, low, high, size):
                if (low, high, size) != (0, 3, 3):
                    raise AssertionError("Unexpected bootstrap population")
                return np.array([0, 0, 1])

        with patch("resumption.analysis.np.random.default_rng", return_value=FixedDraw()):
            observed = paired_gain(predictions, bootstrap_samples=1)
        expected = (2 * math.log(.9 / .5) + math.log(.25 / .5)) / 3
        self.assertEqual(observed["bootstrap_unit"], "task_root_with_all_models_and_repeats")
        np.testing.assert_allclose(observed["log_loss_gain_ci95"], [expected, expected])

    def test_identical_predictors_have_exactly_zero_paired_uncertainty(self):
        predictions = []
        for root_index in range(4):
            for model in ("a", "b"):
                predictions += paired(f"{root_index}-{model}", f"r-{root_index}",
                                      .1 + .2 * root_index, .1 + .2 * root_index,
                                      label=bool(root_index % 2), model=model)
        observed = paired_gain(predictions, bootstrap_samples=200)
        self.assertEqual(observed["log_loss_gain"], 0.)
        self.assertEqual(observed["brier_gain"], 0.)
        self.assertEqual(observed["log_loss_gain_ci95"], [0., 0.])
        self.assertEqual(observed["brier_gain_ci95"], [0., 0.])

    def test_duplicate_predictions_are_rejected_instead_of_overwritten(self):
        predictions = paired("same", "root", .5, .8)
        predictions.append(prediction("same", "root", "static", .1))
        with self.assertRaises(ValueError):
            paired_gain(predictions, bootstrap_samples=0)

    def test_matching_trace_string_does_not_allow_mismatched_model(self):
        predictions = [prediction("same", "root", "static", .5, model="one"),
                       prediction("same", "root", "dynamic", .8, model="another")]
        with self.assertRaises(ValueError):
            paired_gain(predictions, bootstrap_samples=0)


class TransferLeakageTests(unittest.TestCase):
    def test_target_labels_do_not_change_features_regularization_or_predictions(self):
        rows = transfer_fixture()
        first = transfer_fold(rows, "heldout", "lexical")
        changed = [replace(item, correct=not item.correct)
                   if item.model == "heldout" else item for item in rows]
        second = transfer_fold(changed, "heldout", "lexical")
        self.assertEqual(first["feature_manifest"], second["feature_manifest"])
        self.assertEqual(first["feature_manifest"]["training_models"], ["source-a", "source-b"])
        self.assertEqual(first["feature_manifest"]["training_roots"],
                         [f"train-root-{index}" for index in range(4)])
        for method in ("metadata", "static", "dynamic"):
            self.assertEqual(first["methods"][method]["C"], second["methods"][method]["C"])
        probabilities = lambda result: {(p["trace_id"], p["method"]): p["probability"]
                                        for p in result["predictions"]}
        self.assertEqual(probabilities(first), probabilities(second))

    def test_shared_root_across_outer_splits_is_rejected(self):
        rows = transfer_fixture()
        rows.append(replace(rows[0], trace_id="leaking-target", model="heldout", split="test"))
        with self.assertRaises(ValueError):
            transfer_fold(rows, "heldout", "lexical")

    def test_target_vocabulary_and_categories_never_enter_feature_fit(self):
        rows = transfer_fixture()
        train = [item for item in rows if item.model != "heldout" and item.split == "train"]
        fitted = FeatureSpace("lexical").fit(train)
        self.assertNotIn("targetonly", fitted.vectorizer.vocabulary_)
        self.assertNotIn("withheld", fitted.vectorizer.vocabulary_)
        self.assertIn("sourceonly", fitted.vectorizer.vocabulary_)
        target = replace(rows[-1], domain="unseen-domain", difficulty="unseen-difficulty")
        fitted.transform([target], "dynamic")
        self.assertNotIn("unseen-domain", fitted.encoder.categories_[0])
        self.assertNotIn("unseen-difficulty", fitted.encoder.categories_[1])

    def test_same_task_in_source_model_cannot_override_record_root_partition(self):
        records = [dict(trace_id="s", root_id="same-task", model="source", split="train",
                        domain="logic", difficulty="easy", correct=True, text="source words"),
                   dict(trace_id="t", root_id="same-task", model="target", split="test",
                        domain="logic", difficulty="easy", correct=False, text="target words")]
        with self.assertRaises(ValueError):
            validate_records(records)

    def test_unobserved_suffix_cannot_change_prefix_text_or_chunk_boundaries(self):
        prefix = " ".join(f"word{i}" for i in range(64))
        record = dict(trace_id="x", root_id="r", model="m", split="test", domain="logic",
                      difficulty="easy", correct=True, text=prefix + " unobserved suffix")
        first, _ = prefixes([record], 64)
        second, _ = prefixes([{**record, "text": prefix + " a completely different later trace"}], 64)
        self.assertEqual(first[0].text, second[0].text)
        self.assertEqual(first[0].chunks, second[0].chunks)
        self.assertEqual(first[0].spans, second[0].spans)


class OrderControlTests(unittest.TestCase):
    def test_static_predictors_are_order_invariant_in_both_representations(self):
        train = [item for item in transfer_fixture()
                 if item.model != "heldout" and item.split == "train"]
        for representation in ("lexical", "semantic"):
            with self.subTest(representation=representation):
                observed = FeatureSpace(representation, "observed", 0).fit(train)
                shuffled = FeatureSpace(representation, "shuffle", 104729).fit(train)
                reversed_space = FeatureSpace(representation, "reverse", 0).fit(train)
                x = observed.transform(train, "static").toarray()
                np.testing.assert_array_equal(x, shuffled.transform(train, "static").toarray())
                np.testing.assert_array_equal(x, reversed_space.transform(train, "static").toarray())
                # Semantic static includes observed lexical geometry intentionally;
                # its order is held constant when semantic geometry is ablated.
                self.assertEqual(observed.manifest()["vocabulary_digest"],
                                 shuffled.manifest()["vocabulary_digest"])

    def test_order_control_refits_source_and_never_fits_target(self):
        rows = transfer_fixture()
        original_fit = FeatureSpace.fit
        fit_records = []

        def tracked_fit(space, training):
            fit_records.append((space.order, {item.model for item in training},
                                {item.root_id for item in training}))
            return original_fit(space, training)

        with patch.object(FeatureSpace, "fit", tracked_fit):
            transfer_fold(rows, "heldout", "lexical", "observed", 0)
            transfer_fold(rows, "heldout", "lexical", "shuffle", 104729)
        self.assertEqual([record[0] for record in fit_records], ["observed", "shuffle"])
        for _, models, roots in fit_records:
            self.assertNotIn("heldout", models)
            self.assertTrue(all(root.startswith("train-root-") for root in roots))


if __name__ == "__main__":
    unittest.main()
