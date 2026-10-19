"""Offline components of the six E0 checks. This run does not pass E0.

Synthetic phase labels are constructed controls. They are not a human reference
and they are not evidence about model reasoning.
"""
import random

from stage2.segmentation import measure
from stage2.tokenization import ResearchBPE

PHASES = ("planning", "deduction", "verification", "conclusion")
WORDING = {
    "planning": "First we choose the method.",
    "deduction": "Then we compute the intermediate value.",
    "verification": "Next we check the value against the constraint.",
    "conclusion": "Therefore the final answer is ready.",
}
PARAPHRASE = {
    "planning": "The opening move is to select a method.",
    "deduction": "The following step derives an intermediate quantity.",
    "verification": "Afterwards the quantity is tested on the constraint.",
    "conclusion": "At the end the finished answer is stated.",
}
LONG = {
    "planning": "Before any calculation, the solver pauses and chooses a method with care.",
    "deduction": "After that choice, the solver computes an intermediate value from the given numbers.",
    "verification": "Once the value exists, the solver checks it slowly against every stated constraint.",
    "conclusion": "Only after that check does the solver state the final answer in a full sentence.",
}


def _sequence(index):
    order = list(PHASES)
    random.Random(index).shuffle(order)
    return tuple(order)


def _render(order, table):
    parts = [table[phase] for phase in order]
    text = " ".join(parts)
    boundaries = []
    cursor = 0
    for part in parts[:-1]:
        cursor += len(part)
        boundaries.append(cursor)
        cursor += 1
    return text, boundaries, order


def synthetic_items(count=12):
    items = []
    for index in range(count):
        order = _sequence(index)
        text, boundaries, phases = _render(order, WORDING)
        items.append({"item_id": f"synthetic-{index}", "text": text, "boundaries": boundaries, "phases": list(phases)})
    return items


def _boundary_f1(gold, predicted):
    gold, predicted = set(gold), set(predicted)
    if not gold and not predicted:
        return 1.0
    if not predicted or not gold:
        return 0.0
    overlap = len(gold & predicted)
    precision = overlap / len(predicted)
    recall = overlap / len(gold)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _segment_boundaries(text):
    mapping = ResearchBPE().fit([text], ["e0-synthetic"]).mapping(text)
    trace = {"trace_id": "e0", "task_id": "e0", "root_id": "e0", "family": "synthetic", "split": "development",
             "visible_reasoning": text, "raw_response_sha256": "synthetic"}
    rows = measure(trace, "S2", mapping)
    return [row["char_end"] for row in rows[:-1]]


def _recover(text, table):
    mapping = ResearchBPE().fit([text], ["e0-synthetic"]).mapping(text)
    trace = {"trace_id": "e0", "task_id": "e0", "root_id": "e0", "family": "synthetic", "split": "development",
             "visible_reasoning": text, "raw_response_sha256": "synthetic"}
    labels = []
    for row in measure(trace, "S2", mapping):
        labels.append(next((phase for phase, sentence in table.items() if sentence in row["text"]), "unmatched"))
    return labels


def _phase_labels(text, order, table):
    labels = []
    for phase in order:
        if table[phase] in text:
            labels.append(phase)
    return labels


def run():
    items = synthetic_items()
    f1 = [_boundary_f1(item["boundaries"], _segment_boundaries(item["text"])) for item in items]
    boundary = sum(f1) / len(f1)
    paraphrase_hits = 0
    style_hits = 0
    for index, item in enumerate(items):
        order = tuple(item["phases"])
        paraphrase, _, _ = _render(order, PARAPHRASE)
        long_text, _, _ = _render(order, LONG)
        paraphrase_hits += _phase_labels(paraphrase, order, PARAPHRASE) == list(order)
        style_hits += _phase_labels(long_text, order, LONG) == list(order)
    random_hits = 0
    rng = random.Random(5)
    for item in items:
        words = item["text"].split()
        rng.shuffle(words)
        scrambled = " ".join(words)
        recovered = [phase for phase in item["phases"] if WORDING[phase] in scrambled]
        random_hits += recovered == item["phases"]
    return {
        "status": "not_passed",
        "human_reference": "not_completed",
        "scientific_validity": "not_assessed",
        "checks": {
            "synthetic_sequences_with_known_phases": {"items": len(items), "constructed_control": True},
            "segmentation_accuracy": {"sentence_boundary_f1": boundary, "segmenter": "S2", "threshold": "not_assigned"},
            "state_recovery": {
            "constructed_sequence_agreement": sum(
                _recover(item["text"], WORDING) == item["phases"] for item in items) / len(items),
            "model_trace_recovery": "not_run",
            "note": "This uses constructed wording, not a human reference and not model traces.",
        },
            "paraphrase_robustness": {"wording_agreement": paraphrase_hits / len(items)},
            "style_and_length_robustness": {"long_wording_agreement": style_hits / len(items)},
            "random_sequences_do_not_create_false_universality": {
                "scrambled_exact_phase_recovery": random_hits / len(items),
                "interpretation": "A low recovery on scrambled text is a control, not an E0 pass."
            },
        },
    }
