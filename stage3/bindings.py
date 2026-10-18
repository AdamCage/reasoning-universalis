"""Bind embeddings and contextual order by identity, not by list position."""
import math

from measurement.core import text_hash

DIMENSIONS = {"baai/bge-m3": 1024, "qwen/qwen3-embedding-8b": 4096}


def require_trajectory_order(rows):
    """Fail closed. Do not sort a shuffled segment list into a plausible context."""
    groups = {}
    for row in rows:
        groups.setdefault((row["trace_id"], row["measurement_config_digest"]), []).append(row)
    for seq in groups.values():
        if [row["position"] for row in seq] != list(range(len(seq))):
            raise ValueError("Segment order is not trajectory order")
        digest = seq[0]["trace_sha256"]
        for previous, current in zip(seq, seq[1:]):
            if previous["char_end"] != current["char_start"] or current["trace_sha256"] != digest:
                raise ValueError("Segment boundaries are not one contiguous trace")
    return rows


def embedding_texts(rows, context_mode):
    """Full registered embedder input. Contextual uses the two previous segments, capped at 1000 characters."""
    if context_mode not in ("Local", "Contextual"):
        raise ValueError("Unknown embedding condition")
    require_trajectory_order(rows)
    histories = {}
    texts = []
    for row in rows:
        history = histories.setdefault((row["trace_id"], row["measurement_config_digest"]), [])
        context = "".join(item["text"] for item in history[-2:])[-1000:] if context_mode == "Contextual" else ""
        history.append(row)
        texts.append(context + row["text"])
    return texts


def align_embeddings(rows, records, model_id, dimension, context_mode="Local"):
    if model_id not in DIMENSIONS or dimension != DIMENSIONS[model_id]:
        raise ValueError("Embedding configuration dimension is not the registered one")
    texts = embedding_texts(rows, context_mode)
    by_id = {}
    for record in records:
        segment_id = record.get("segment_id")
        if segment_id in by_id:
            raise ValueError("Duplicate embedding for one segment")
        if record.get("model_id") != model_id:
            raise ValueError("Embedding model does not match the measurement configuration")
        vector = record.get("vector")
        if type(vector) is not list or len(vector) != dimension or any(
                isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in vector):
            raise ValueError("Embedding vector does not match the configured dimension")
        by_id[segment_id] = record
    if set(by_id) != {row["segment_id"] for row in rows}:
        raise ValueError("Embedding roster does not match the segments")
    aligned = []
    for row, text in zip(rows, texts):
        record = by_id[row["segment_id"]]
        if record.get("input_sha256") != text_hash(text):
            raise ValueError("Embedding input does not match the registered " + context_mode + " input")
        if record.get("trace_sha256") != row["trace_sha256"]:
            raise ValueError("Embedding trace binding drifted")
        aligned.append(record["vector"])
    return aligned
