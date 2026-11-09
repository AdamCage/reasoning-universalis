"""Leakage-safe, fixed-prefix transfer analysis of observable reasoning text.

This module tests predictive utility of text representations, not validity of
functional reasoning roles or access to internal computation.  Only source
models and source training roots enter any fit.  Source validation roots select
regularization; each target model is evaluated on the disjoint test roots.

The token unit is a non-whitespace span, explicitly not a model-native token.
Embeddings must cover exact 16-word chunks within the observed prefix.  No
full-trace length, answer text, target labels, or target representation fit is
used to construct the predictors.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import OneHotEncoder, StandardScaler


VERSION = "observable-prefix-transfer-v1.1"
CHUNK_WORDS = 16
DEFAULT_BUDGETS = (128, 256, 512)
C_GRID = (0.01, 0.1, 1.0)
PERMUTATION_SEEDS = (104729, 130363, 155921)
ALLOWED_EMBEDDERS = ("baai/bge-m3", "qwen/qwen3-embedding-8b")
GEOMETRY_NAMES = (
    "adjacent_distance_mean", "adjacent_distance_sd", "adjacent_distance_slope",
    "lag_two_distance_mean", "endpoint_distance", "path_efficiency",
    "turning_cosine_mean", "nonadjacent_revisit_rate", "nonadjacent_nearest_distance",
    "early_late_centroid_distance", "displacement_from_start_slope",
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_records(path: str | Path, allow_admission_smoke: bool = False) -> list[dict]:
    """Read runner JSON or observation JSONL without promoting admission data."""
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        document = [json.loads(line) for line in text.splitlines() if line.strip()]
    phase = None
    if isinstance(document, dict):
        phase = document.get("phase")
        if "records" in document:
            rows = document["records"]
        elif "trace_id" in document:
            rows = [document]
        else:
            raise ValueError("Observation document has no records list")
    else:
        rows = document
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Observation input must contain a list of records")
    phases = {row.get("phase") for row in rows} | {phase}
    if "admission" in phases and not allow_admission_smoke:
        raise ValueError("Admission records are smoke-only; use --allow-admission-smoke explicitly")
    if phases - {None, "collection", "admission"}:
        raise ValueError("Unrecognized observation phase")
    return rows


def word_spans(text: str) -> list[tuple[int, int]]:
    """Unicode Python character offsets of the preregistered whitespace unit."""
    return [(match.start(), match.end()) for match in re.finditer(r"\S+", text)]


def chunk_spans(text: str, budget: int, chunk_words: int = CHUNK_WORDS) -> list[dict]:
    """Return exact prefix chunks, never reading text after the observed budget."""
    if type(budget) is not int or budget <= 0 or budget % chunk_words:
        raise ValueError("Budget must be a positive multiple of chunk_words")
    spans = word_spans(text)
    if len(spans) < budget:
        raise ValueError("Trace is shorter than the observed-word budget")
    return [{"start": spans[index][0], "end": spans[index + chunk_words - 1][1],
             "text": text[spans[index][0]:spans[index + chunk_words - 1][1]]}
            for index in range(0, budget, chunk_words)]


@dataclass(frozen=True)
class Prefix:
    trace_id: str
    root_id: str
    model: str
    split: str
    domain: str
    difficulty: str
    correct: bool
    text: str
    chunks: tuple[str, ...]
    spans: tuple[tuple[int, int], ...]
    vectors: Any = None


def _semantic_vectors(record: dict, chunks: list[dict], embedder: str) -> np.ndarray:
    if embedder not in ALLOWED_EMBEDDERS:
        raise ValueError("Only the two specified verified embedding identities are allowed")
    if "embeddings" in record:
        rows = record["embeddings"].get(embedder, [])
    elif record.get("embedding_model") == embedder:
        rows = record.get("embedding_segments", [])
    else:
        rows = []
    indexed = {}
    for row in rows:
        key = (row.get("start"), row.get("end"))
        if key in indexed:
            raise ValueError("Duplicate embedding span")
        indexed[key] = row
    selected = []
    for chunk in chunks:
        row = indexed.get((chunk["start"], chunk["end"]))
        if row is None or row.get("text") != chunk["text"]:
            raise ValueError("Missing or mismatched exact-prefix embedding chunk")
        if row.get("identity_verified") is not True:
            raise ValueError("Embedding identity has not been verified")
        if row.get("input_sha256") != hashlib.sha256(chunk["text"].encode()).hexdigest():
            raise ValueError("Embedding input digest mismatch")
        if row.get("model_id", embedder) != embedder:
            raise ValueError("Embedding model identity drift")
        vector = np.asarray(row.get("vector"), dtype=float)
        if vector.ndim != 1 or not len(vector) or not np.all(np.isfinite(vector)):
            raise ValueError("Malformed embedding vector")
        if not np.linalg.norm(vector):
            raise ValueError("Zero semantic embedding vector")
        selected.append(vector)
    if len({len(vector) for vector in selected}) != 1:
        raise ValueError("Embedding dimension changed within a prefix")
    expected_dimension = 1024 if embedder == "baai/bge-m3" else None
    if expected_dimension and len(selected[0]) != expected_dimension:
        raise ValueError("BGE-M3 embedding dimension must be 1024")
    if embedder == "qwen/qwen3-embedding-8b" and len(selected[0]) > 4096:
        raise ValueError("Qwen3-Embedding-8B dimension must not exceed 4096")
    return np.stack(selected)


def validate_records(records: list[dict]) -> None:
    roots: dict[str, str] = {}
    traces = set()
    for row in records:
        for key in ("trace_id", "root_id", "model", "split", "domain", "difficulty"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError("Missing or invalid record field: " + key)
        if row["trace_id"] in traces:
            raise ValueError("Duplicate trace identity")
        traces.add(row["trace_id"])
        split = {"validation": "val"}.get(row["split"], row["split"])
        if split not in ("train", "val", "test"):
            raise ValueError("Unrecognized split")
        root = row["root_id"]
        if root in roots and roots[root] != split:
            raise ValueError("A task root crosses split boundaries")
        roots[root] = split
        completed = row.get("status", "completed") == "completed"
        if not isinstance(row.get("text"), str) or (completed and not row["text"]):
            raise ValueError("Completed observations require nonempty reasoning text")
        ungradeable = row.get("correct") is None and row.get("gradable") is False
        if completed and type(row.get("correct")) is not bool and not ungradeable:
            raise ValueError("Correctness must be an independently verified Boolean")
        if not completed and row.get("correct") is not None and type(row["correct"]) is not bool:
            raise ValueError("Noncompleted observation correctness must be Boolean or null")
        if completed and "ANSWER:" in row["text"]:
            raise ValueError("Reasoning text contains an answer marker; censor it upstream")


def prefixes(records: list[dict], budget: int, embedder: str | None = None) -> tuple[list[Prefix], dict]:
    if type(budget) is not int or budget <= 0 or budget % CHUNK_WORDS:
        raise ValueError("Budget must be a positive multiple of chunk_words")
    validate_records(records)
    result, coverage = [], defaultdict(Counter)
    embedding_dimension = None
    for row in records:
        key = "|".join((row["model"], row["domain"], row["split"], str(row.get("correct"))))
        coverage[key]["attempted_records"] += 1
        if row.get("status", "completed") != "completed":
            coverage[key]["not_completed"] += 1
            continue
        if row.get("gradable") is False or row.get("correct") is None:
            coverage[key]["grading_unavailable"] += 1
            continue
        try:
            chunks = chunk_spans(row["text"], budget)
        except ValueError:
            coverage[key]["shorter_than_budget"] += 1
            continue
        try:
            vectors = _semantic_vectors(row, chunks, embedder) if embedder else None
        except (ValueError, TypeError, KeyError) as exc:
            coverage[key]["embedding_excluded:" + str(exc)] += 1
            continue
        if vectors is not None:
            dimension = vectors.shape[1]
            if embedding_dimension is not None and embedding_dimension != dimension:
                raise ValueError("Embedding dimension changed across eligible observations")
            embedding_dimension = dimension
        split = {"validation": "val"}.get(row["split"], row["split"])
        result.append(Prefix(row["trace_id"], row["root_id"], row["model"], split,
                             row["domain"], row["difficulty"], row["correct"],
                             row["text"][:chunks[-1]["end"]], tuple(c["text"] for c in chunks),
                             tuple((c["start"], c["end"]) for c in chunks), vectors))
        coverage[key]["eligible"] += 1
    return result, {key: dict(value) for key, value in sorted(coverage.items())}


def matched_prefixes(records: list[dict], comparison_records: list[dict], budget: int,
                     embedder: str, comparison_embedder: str) -> tuple[list[Prefix], dict, dict]:
    """Intersect exact eligible prefixes before any source or target fit.

    This is a supplementary embedding comparison. The ordinary primary BGE
    analysis continues to use its original eligible population. Run this helper
    symmetrically for both embedders to fit each on the same train/val/test rows.
    """
    if embedder not in ALLOWED_EMBEDDERS or comparison_embedder not in ALLOWED_EMBEDDERS:
        raise ValueError("Matched comparison requires the two allowed embedding identities")
    if embedder == comparison_embedder:
        raise ValueError("Matched comparison requires two different embedders")
    rows, coverage = prefixes(records, budget, embedder)
    comparison_rows, comparison_coverage = prefixes(comparison_records, budget, comparison_embedder)
    primary_records = {row["trace_id"]: row for row in records}
    other_records = {row["trace_id"]: row for row in comparison_records}
    identity = ("root_id", "model", "domain", "difficulty", "correct", "text", "task_id",
                "sample_index", "provider", "response_sha256")
    for trace_id in primary_records.keys() & other_records.keys():
        first, second = primary_records[trace_id], other_records[trace_id]
        first_split = {"validation": "val"}.get(first["split"], first["split"])
        second_split = {"validation": "val"}.get(second["split"], second["split"])
        if (any(first.get(key) != second.get(key) for key in identity) or
                first_split != second_split or
                first.get("status", "completed") != second.get("status", "completed")):
            raise ValueError("Matched embedding inputs disagree on trace identity: " + trace_id)
    first_ids = {row.trace_id for row in rows}
    second_ids = {row.trace_id for row in comparison_rows}
    common = first_ids & second_ids
    matched = [row for row in rows if row.trace_id in common]
    counts = Counter("|".join((row.model, row.domain, row.split, str(row.correct))) for row in matched)
    details = {
        "scope": "supplementary_matched_embeddings_primary_estimand_unchanged",
        "embedding_model": embedder, "comparison_embedding_model": comparison_embedder,
        "comparison_record_digest": digest(comparison_records),
        "matching_unit": "exact_trace_prefix_before_all_train_validation_test_fits",
        "budget_words": budget,
        "primary_eligible": len(rows), "comparison_eligible": len(comparison_rows),
        "matched_eligible": len(matched), "matched_roots": len({row.root_id for row in matched}),
        "matched_trace_ids": sorted(common), "matched_counts": dict(sorted(counts.items())),
        "primary_excluded_trace_ids": sorted(first_ids - common),
        "comparison_excluded_trace_ids": sorted(second_ids - common),
        "comparison_coverage": comparison_coverage,
        "limitation": "Matching selects a common observed population; it does not recover missing embeddings.",
    }
    return matched, coverage, details


def unit_rows(vectors: Any) -> np.ndarray:
    values = np.asarray(vectors, dtype=float)
    if values.ndim != 2 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("Geometry requires a finite nonempty vector matrix")
    norm = np.linalg.norm(values, axis=1, keepdims=True)
    return np.divide(values, norm, out=np.zeros_like(values), where=norm > 0)


def _slope(values: Any) -> float:
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return 0.0
    times = np.linspace(0.0, 1.0, len(values))
    return float(np.dot(times - times.mean(), values - values.mean()) /
                 np.dot(times - times.mean(), times - times.mean()))


def geometry(vectors: Any) -> np.ndarray:
    """Descriptive path statistics; no functional-role interpretation is attached."""
    points = unit_rows(vectors)
    if len(points) < 4:
        raise ValueError("At least four chunks are needed for geometry")
    similarities = np.clip(points @ points.T, -1, 1)
    distances = 1.0 - similarities
    adjacent = np.diag(distances, 1)
    lag_two = np.diag(distances, 2)
    displacement = np.linalg.norm(points[-1] - points[0])
    path_length = np.linalg.norm(np.diff(points, axis=0), axis=1).sum()
    increments = np.diff(points, axis=0)
    increments = unit_rows(increments)
    turns = np.sum(increments[:-1] * increments[1:], axis=1)
    distant = distances[np.triu_indices(len(points), 2)]
    nearest_previous = [min(distances[index, :index - 1]) for index in range(2, len(points))]
    middle = len(points) // 2
    early = points[:middle].mean(axis=0)
    late = points[middle:].mean(axis=0)
    centroid_norms = np.linalg.norm(early) * np.linalg.norm(late)
    early_late = 1.0 - float(np.dot(early, late) / centroid_norms) if centroid_norms else 0.0
    features = np.array([
        adjacent.mean(), adjacent.std(), _slope(adjacent), lag_two.mean(),
        distances[0, -1], displacement / path_length if path_length else 0.0,
        turns.mean(), np.mean(distant <= 0.1), np.mean(nearest_previous),
        early_late, _slope(distances[0]),
    ], dtype=float)
    if features.shape != (len(GEOMETRY_NAMES),) or not np.all(np.isfinite(features)):
        raise ValueError("Non-finite geometry")
    return features


def order_indices(count: int, trace_id: str, order: str, seed: int) -> np.ndarray:
    indices = np.arange(count)
    if order == "reverse":
        return indices[::-1]
    if order == "shuffle":
        key = int(hashlib.sha256(f"{seed}:{trace_id}".encode()).hexdigest()[:16], 16)
        return np.random.default_rng(key).permutation(indices)
    if order != "observed":
        raise ValueError("Unknown ordering")
    return indices


def basic_features(prefix: Prefix) -> np.ndarray:
    text = prefix.text
    words = re.findall(r"\w+", text.casefold())
    count = max(1, len(words))
    uncertainty = {"maybe", "perhaps", "uncertain", "unsure", "possibly", "might", "seems"}
    correction = {"wait", "instead", "mistake", "wrong", "reconsider", "actually", "however"}
    return np.array([
        math.log1p(len(text)), sum(c.isdigit() for c in text) / max(1, len(text)),
        sum(c in ".,;:!?()[]{}=+-*/" for c in text) / max(1, len(text)),
        text.count("\n") / count, len(set(words)) / count,
        sum(word in uncertainty for word in words) / count,
        sum(word in correction for word in words) / count,
    ])


def root_weights(rows: list[Prefix]) -> np.ndarray:
    counts = Counter(row.root_id for row in rows)
    # Mean one for comparable regularization across data sizes, equal total per root.
    values = np.array([1.0 / counts[row.root_id] for row in rows])
    return values * len(values) / values.sum()


class FeatureSpace:
    """All learned vocabulary, scaling and categorical levels are source-train only."""

    def __init__(self, representation: str, order: str = "observed", seed: int = 0):
        if representation not in ("lexical", "semantic"):
            raise ValueError("Unknown representation")
        self.representation, self.order, self.seed = representation, order, seed
        self.vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 1),
                                         min_df=1, max_features=4096, sublinear_tf=True,
                                         token_pattern=r"(?u)\b\w+\b")
        self.encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
        self.scalers: dict[str, StandardScaler] = {}

    def _numeric(self, rows: list[Prefix], method: str) -> np.ndarray:
        result = []
        for row in rows:
            values = [basic_features(row)]
            lexical = self.vectorizer.transform(row.chunks).toarray()
            indices = order_indices(len(row.chunks), row.trace_id, self.order, self.seed)
            if method != "metadata":
                # Static pooled lexical content is invariant to order.
                values.append(lexical.mean(axis=0))
            if self.representation == "semantic" and method != "metadata":
                semantic = unit_rows(row.vectors)
                values.append(semantic.mean(axis=0))
                # Lexical geometry is a confound baseline for semantic geometry.
                values.append(geometry(lexical))
            if method == "dynamic":
                vectors = row.vectors if self.representation == "semantic" else lexical
                values.append(geometry(np.asarray(vectors)[indices]))
            result.append(np.concatenate(values))
        return np.stack(result)

    def fit(self, rows: list[Prefix]) -> "FeatureSpace":
        if not rows or any(row.split != "train" for row in rows):
            raise ValueError("Feature fit is restricted to source training roots")
        self.training_roots = sorted({row.root_id for row in rows})
        self.training_models = sorted({row.model for row in rows})
        self.vectorizer.fit([row.text for row in rows])
        self.encoder.fit([[row.domain, row.difficulty] for row in rows])
        for method in ("metadata", "static", "dynamic"):
            self.scalers[method] = StandardScaler().fit(self._numeric(rows, method))
        return self

    def transform(self, rows: list[Prefix], method: str) -> sparse.csr_matrix:
        numeric = self.scalers[method].transform(self._numeric(rows, method))
        categories = self.encoder.transform([[row.domain, row.difficulty] for row in rows])
        pieces = [sparse.csr_matrix(numeric), categories]
        if method != "metadata":
            pieces.append(self.vectorizer.transform([row.text for row in rows]))
        return sparse.hstack(pieces, format="csr")

    def manifest(self) -> dict:
        return {"training_roots": self.training_roots, "training_models": self.training_models,
                "vocabulary_digest": digest({word: int(index) for word, index in self.vectorizer.vocabulary_.items()}),
                "idf_digest": digest(self.vectorizer.idf_.tolist()),
                "categories": [values.tolist() for values in self.encoder.categories_],
                "scaler_digest": digest({key: {"mean": value.mean_.tolist(),
                                                 "scale": value.scale_.tolist()}
                                          for key, value in self.scalers.items()}),
                "representation": self.representation, "order": self.order, "seed": self.seed}

    def lexical_chunk_coverage(self, rows: list[Prefix]) -> dict:
        """Diagnose OOV chunks without changing features or eligible rows."""
        counts = Counter(chunks=0, zero_chunks=0, traces=0,
                         traces_with_zero_chunks=0, entirely_zero_traces=0)
        for row in rows:
            empty = np.asarray(self.vectorizer.transform(row.chunks).getnnz(axis=1)) == 0
            counts["chunks"] += len(empty)
            counts["zero_chunks"] += int(empty.sum())
            counts["traces"] += 1
            counts["traces_with_zero_chunks"] += int(empty.any())
            counts["entirely_zero_traces"] += int(empty.all())
        return {**dict(counts), "zero_chunk_fraction": counts["zero_chunks"] / counts["chunks"]
                if counts["chunks"] else None,
                "zero_vector_handling": "unchanged_cosine_geometry_zero_rows_reported_as_coverage"}


def metrics(labels: Any, probabilities: Any, weights: Any = None) -> dict:
    labels, probabilities = np.asarray(labels, dtype=float), np.asarray(probabilities, dtype=float)
    if len(labels) != len(probabilities) or not len(labels):
        raise ValueError("Metrics need aligned nonempty labels and probabilities")
    probabilities = np.clip(probabilities, 1e-8, 1 - 1e-8)
    weights = np.ones(len(labels)) if weights is None else np.asarray(weights, dtype=float)
    log_loss = -np.average(labels * np.log(probabilities) + (1 - labels) * np.log(1 - probabilities), weights=weights)
    return {"log_loss": float(log_loss),
            "brier": float(np.average((labels - probabilities) ** 2, weights=weights)),
            "accuracy": float(np.average((probabilities >= 0.5) == labels, weights=weights)),
            "auroc": float(roc_auc_score(labels, probabilities, sample_weight=weights))
                     if len(set(labels)) > 1 else None,
            "correct_rate": float(np.average(labels, weights=weights)),
            "rows": len(labels)}


def _fit_predict(train_x: Any, train_y: np.ndarray, weights: np.ndarray,
                 evaluation_x: Any, c_value: float) -> tuple[np.ndarray, str]:
    if len(set(train_y)) == 1:
        probability = float((np.dot(weights, train_y) + 1) / (weights.sum() + 2))
        return np.full(evaluation_x.shape[0], probability), "smoothed_constant_one_training_class"
    classifier = LogisticRegression(C=c_value, solver="liblinear", max_iter=1000,
                                    random_state=0, fit_intercept=True)
    classifier.fit(train_x, train_y, sample_weight=weights)
    return classifier.predict_proba(evaluation_x)[:, 1], "logistic_regression"


def transfer_fold(rows: list[Prefix], target_model: str, representation: str,
                  order: str = "observed", seed: int = 0) -> dict:
    training = [row for row in rows if row.model != target_model and row.split == "train"]
    validation = [row for row in rows if row.model != target_model and row.split == "val"]
    testing = [row for row in rows if row.model == target_model and row.split == "test"]
    if not training or not validation or not testing:
        return {"target_model": target_model, "status": "unavailable", "reason": "empty_train_validation_or_test",
                "counts": {"train": len(training), "val": len(validation), "test": len(testing)}}
    if len({row.model for row in training}) < 2:
        source_limit = "Only one source model; no two-source transfer claim"
    else:
        source_limit = None
    if ({row.root_id for row in training} & {row.root_id for row in validation} or
            {row.root_id for row in training + validation} & {row.root_id for row in testing}):
        raise ValueError("Root leakage into outer target evaluation")
    space = FeatureSpace(representation, order, seed).fit(training)
    if target_model in space.training_models:
        raise ValueError("Target model entered a representation fit")
    training_y = np.array([row.correct for row in training], dtype=int)
    validation_y = np.array([row.correct for row in validation], dtype=int)
    testing_y = np.array([row.correct for row in testing], dtype=int)
    fitted = {}
    predictions = []
    for method in ("metadata", "static", "dynamic"):
        train_x, val_x, test_x = (space.transform(subset, method) for subset in (training, validation, testing))
        candidates = []
        for c_value in C_GRID:
            probabilities, estimator = _fit_predict(train_x, training_y, root_weights(training), val_x, c_value)
            candidates.append((metrics(validation_y, probabilities, root_weights(validation))["log_loss"], c_value))
        best_loss, c_value = min(candidates)
        probabilities, estimator = _fit_predict(train_x, training_y, root_weights(training), test_x, c_value)
        fitted[method] = {"C": c_value, "source_validation_log_loss": best_loss,
                          "estimator": estimator, "test": metrics(testing_y, probabilities, root_weights(testing))}
        for row, probability in zip(testing, probabilities):
            predictions.append({"trace_id": row.trace_id, "root_id": row.root_id, "model": row.model,
                                "domain": row.domain, "difficulty": row.difficulty, "correct": row.correct,
                                "method": method, "probability": float(probability)})
    return {"target_model": target_model, "status": "evaluated", "limitation": source_limit,
            "counts": {"train": len(training), "val": len(validation), "test": len(testing)},
            "training_root_count": len({row.root_id for row in training}),
            "validation_roots": sorted({row.root_id for row in validation}),
            "test_roots": sorted({row.root_id for row in testing}),
            "lexical_chunk_coverage": {name: space.lexical_chunk_coverage(subset)
                                       for name, subset in (("train", training), ("val", validation),
                                                            ("test", testing))},
            "feature_manifest": space.manifest(), "methods": fitted, "predictions": predictions}


def paired_gain(predictions: list[dict], reference: str = "static", candidate: str = "dynamic",
                bootstrap_samples: int = 2000, seed: int = 271828) -> dict:
    """Equal-root paired differences; bootstrap a root with all models/repeats."""
    if type(bootstrap_samples) is not int or bootstrap_samples < 0:
        raise ValueError("Bootstrap samples must be a nonnegative integer")
    by_trace: dict[str, dict] = defaultdict(dict)
    for prediction in predictions:
        if prediction["method"] in by_trace[prediction["trace_id"]]:
            raise ValueError("Duplicate trace/method prediction")
        by_trace[prediction["trace_id"]][prediction["method"]] = prediction
    groups = defaultdict(list)
    for methods in by_trace.values():
        if reference not in methods or candidate not in methods:
            continue
        first, second = methods[reference], methods[candidate]
        identity = ("root_id", "correct", "model", "domain", "difficulty")
        if any(first.get(key) != second.get(key) for key in identity):
            raise ValueError("Unpaired prediction identity")
        label = float(first["correct"])
        p0, p1 = np.clip([first["probability"], second["probability"]], 1e-8, 1 - 1e-8)
        loss0 = -(label * math.log(p0) + (1 - label) * math.log(1 - p0))
        loss1 = -(label * math.log(p1) + (1 - label) * math.log(1 - p1))
        groups[first["root_id"]].append((loss0 - loss1, (label - p0) ** 2 - (label - p1) ** 2))
    if not groups:
        return {"status": "unavailable", "reason": "no_aligned_predictions"}
    values = np.array([np.mean(group, axis=0) for _, group in sorted(groups.items())])
    result = {"status": "estimated", "root_count": len(groups),
              "trace_count": sum(map(len, groups.values())), "positive_means_candidate_improves": True,
              "log_loss_gain": float(values[:, 0].mean()), "brier_gain": float(values[:, 1].mean()),
              "bootstrap_unit": "task_root_with_all_models_and_repeats",
              "uncertainty_scope": "conditional_on_fitted_models_and_observed_roots",
              "interval_status": "not_requested" if not bootstrap_samples else "estimated",
              "bootstrap_samples": bootstrap_samples, "bootstrap_seed": seed}
    if bootstrap_samples and len(groups) < 2:
        result.update(interval_status="not_estimated_insufficient_independent_roots",
                      interval_limitation="One task root cannot estimate between-root uncertainty; the point estimate is descriptive only.",
                      log_loss_gain_ci95=None, brier_gain_ci95=None)
        return result
    if bootstrap_samples:
        rng = np.random.default_rng(seed)
        estimates = np.stack([values[rng.integers(0, len(values), len(values))].mean(axis=0)
                              for _ in range(bootstrap_samples)])
        result["log_loss_gain_ci95"] = np.quantile(estimates[:, 0], [0.025, 0.975]).tolist()
        result["brier_gain_ci95"] = np.quantile(estimates[:, 1], [0.025, 0.975]).tolist()
    return result


def run_analysis(records: list[dict], budgets: tuple[int, ...] = DEFAULT_BUDGETS,
                 embedder: str | None = None, bootstrap_samples: int = 2000,
                 include_order_controls: bool = True, matched_records: list[dict] | None = None,
                 matched_embedder: str | None = None) -> dict:
    validate_records(records)
    if (matched_records is None) != (matched_embedder is None):
        raise ValueError("Matched records and companion embedding model must be supplied together")
    if matched_records is not None and embedder is None:
        raise ValueError("Matched embedding analysis requires a primary embedding model")
    if not budgets or any(type(budget) is not int or budget < 4 * CHUNK_WORDS or
                          budget % CHUNK_WORDS for budget in budgets):
        raise ValueError("Analysis budgets require at least four complete chunks")
    models = sorted({record["model"] for record in records})
    representation = "semantic" if embedder else "lexical"
    runs, order_contrasts = [], []
    for budget in budgets:
        matching = None
        if matched_records is None:
            rows, coverage = prefixes(records, budget, embedder)
        else:
            rows, coverage, matching = matched_prefixes(records, matched_records, budget,
                                                        embedder, matched_embedder)
        observed_dynamic = None
        conditions = [("observed", 0)]
        if include_order_controls:
            conditions += [("reverse", 0)] + [("shuffle", seed) for seed in PERMUTATION_SEEDS]
        for order, seed in conditions:
            folds = [transfer_fold(rows, target, representation, order, seed) for target in models]
            predictions = [prediction for fold in folds for prediction in fold.get("predictions", [])]
            runs.append({"budget_words": budget, "order": order, "order_seed": seed,
                         "coverage": coverage, "eligible_rows": len(rows), "folds": folds,
                         "matched_embedding_coverage": matching,
                         "paired_gain": paired_gain(predictions, bootstrap_samples=bootstrap_samples),
                         "paired_gain_by_target": {
                             fold["target_model"]: paired_gain(fold.get("predictions", []),
                                                               bootstrap_samples=bootstrap_samples)
                             for fold in folds}})
            dynamic = [prediction for prediction in predictions if prediction["method"] == "dynamic"]
            if order == "observed":
                observed_dynamic = dynamic
            else:
                if observed_dynamic is None:
                    raise ValueError("Order controls require an observed reference")
                paired = [{**prediction, "method": "observed_dynamic"} for prediction in observed_dynamic]
                paired += [{**prediction, "method": "control_dynamic"} for prediction in dynamic]
                order_contrasts.append({
                    "budget_words": budget, "control_order": order, "control_seed": seed,
                    "estimand": "control_refitted_dynamic_loss_minus_observed_dynamic_loss",
                    "multiplicity": "exploratory_separate_contrasts_not_adjusted",
                    "paired_gain": paired_gain(paired, reference="control_dynamic", candidate="observed_dynamic",
                                               bootstrap_samples=bootstrap_samples),
                    "paired_gain_by_target": {
                        target: paired_gain([prediction for prediction in paired if prediction["model"] == target],
                                            reference="control_dynamic", candidate="observed_dynamic",
                                            bootstrap_samples=bootstrap_samples)
                        for target in models},
                })
    return {"analysis_version": VERSION, "record_count": len(records),
            "record_digest": digest(records), "representation": representation,
            "embedding_model": embedder, "word_unit": "Unicode non-whitespace span",
            "analysis_population": "supplementary_matched_embedding_prefixes" if matched_records is not None
                                   else "original_embedder_specific_eligible_prefixes",
            "matched_embedding_model": matched_embedder,
            "chunk_words": CHUNK_WORDS, "C_grid": list(C_GRID), "models": models,
            "scientific_status": "exploratory_predictive_audit_not_H1_H7_validation",
            "E0": "not_passed", "functional_state_labels_used": False,
            "limitations": ["Observable reasoning text is not complete internal computation.",
                            "Eligibility requires a trace to reach the fixed budget; coverage can depend on correctness.",
                            "Heldout task roots belong to the same programmed benchmark distribution.",
                            "Performance differences do not demonstrate causal benefits of stopping.",
                            "Bootstrap intervals condition on fitted predictors; training uncertainty is not integrated.",
                            "Source-vocabulary OOV chunks remain zero vectors in lexical geometry; their frequency is reported per fold.",
                            "Regularization selection uses source validation only; fitted predictors are not refit on validation."],
            "runs": runs, "order_contrasts": order_contrasts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="Runner JSON, JSON list, or JSONL observation records")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budgets", default=",".join(map(str, DEFAULT_BUDGETS)))
    parser.add_argument("--embedding-model", choices=ALLOWED_EMBEDDERS)
    parser.add_argument("--matched-embedding-input", type=Path,
                        help="Supplementary only: intersect exact prefixes with the other embedder before all fits")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--no-order-controls", action="store_true")
    parser.add_argument("--allow-admission-smoke", action="store_true",
                        help="Allow admission-only records for implementation smoke checks, never findings")
    args = parser.parse_args()
    records = read_records(args.records, args.allow_admission_smoke)
    matched_records, matched_embedder = None, None
    if args.matched_embedding_input is not None:
        if args.embedding_model is None:
            parser.error("--matched-embedding-input requires --embedding-model")
        matched_embedder = next(model for model in ALLOWED_EMBEDDERS if model != args.embedding_model)
        matched_records = read_records(args.matched_embedding_input, args.allow_admission_smoke)
    result = run_analysis(records, tuple(map(int, args.budgets.split(","))), args.embedding_model,
                          args.bootstrap_samples, not args.no_order_controls, matched_records, matched_embedder)
    result["admission_smoke_override"] = args.allow_admission_smoke
    if args.allow_admission_smoke:
        result["scientific_status"] = "implementation_smoke_only_no_scientific_findings"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"output": str(args.output), "records": len(records),
                      "representation": result["representation"], "runs": len(result["runs"])}))


if __name__ == "__main__":
    main()
