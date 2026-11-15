from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

VERSION = "cross-model-2026-11-15-v1"
ARTIFACT = "artifacts/cross-model-2026-11-15"
PROTOCOL = "design/CROSS_MODEL_PROTOCOL_2026_11_15.json"
PARENT = "artifacts/machine-annotation-development-2026-11-08"
ROUTES = (("qwen/qwen3-32b", "DeepInfra"), ("openai/gpt-oss-20b", "DeepInfra"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rank(purpose, value):
    return sha(canonical([VERSION, purpose, value]))


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def immutable(path, value):
    path = Path(path)
    data = canonical(value) + b"\n"
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Frozen cross-model artifact differs: " + path.name)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def utcnow():
    return datetime.now(timezone.utc).isoformat()
