#!/usr/bin/env bash
# On each boot, materialize a gitignored .env from env.example when the
# Cursor Cloud secret ROUTERAI_API_KEY is present. Never print the key.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

python3 - << 'PY'
import os
import stat
from pathlib import Path

key = os.environ.get("ROUTERAI_API_KEY", "")
if not key or any(ch in key for ch in "\r\n\x00"):
    raise SystemExit(0)

example = Path("env.example")
target = Path(".env")
if not example.is_file():
    raise SystemExit(0)

if target.is_file():
    for line in target.read_text(encoding="utf-8").splitlines():
        if line.startswith("ROUTERAI_API_KEY="):
            current = line.split("=", 1)[1].strip().strip('"').strip("'")
            if current:
                raise SystemExit(0)

lines = []
replaced = False
for line in example.read_text(encoding="utf-8").splitlines():
    if line.startswith("ROUTERAI_API_KEY="):
        lines.append("ROUTERAI_API_KEY=" + key)
        replaced = True
    else:
        lines.append(line)
if not replaced:
    lines.append("ROUTERAI_API_KEY=" + key)

target.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
PY
