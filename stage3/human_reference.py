"""Build the blinded annotation packet. It does not contain human labels."""
import json
from pathlib import Path

from stage3.e0_offline import WORDING, synthetic_items

ROOT = Path(__file__).resolve().parents[1]
ITEMS_PATH = ROOT / "design" / "HUMAN_REFERENCE_ITEMS.json"
KEY_PATH = ROOT / "design" / "HUMAN_REFERENCE_CONSTRUCTED_KEY.json"


def packet():
    items = []
    key = []
    for item in synthetic_items():
        segments = []
        cursor = 0
        phases = item["phases"]
        for index, phase in enumerate(phases):
            text = WORDING[phase]
            segments.append({"segment_id": f"{item['item_id']}:{index}", "text": text,
                             "previous_texts": [segment["text"] for segment in segments[-2:]]})
            key.append({"segment_id": f"{item['item_id']}:{index}", "constructed_phase": phase,
                        "char_start": cursor, "char_end": cursor + len(text)})
            cursor += len(text) + 1
        items.append({"item_id": item["item_id"], "segments": segments})
    return {
        "schema_version": 1,
        "status": "awaiting_human_annotation",
        "blinded": True,
        "shows_model_identity": False,
        "shows_correctness": False,
        "items": items,
    }, {
        "schema_version": 1,
        "status": "constructed_control_not_human_gold",
        "use": "Do not give this file to the annotator.",
        "labels": key,
    }


def write():
    items, key = packet()
    ITEMS_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    KEY_PATH.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
