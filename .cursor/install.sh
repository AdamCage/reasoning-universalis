#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap. uv must land on the default PATH:
# login shells return before ~/.bashrc, so ~/.local/bin is not visible.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -x "${HOME}/.local/bin/uv" ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

sudo ln -sfn "${HOME}/.local/bin/uv" /usr/local/bin/uv
if [[ -x "${HOME}/.local/bin/uvx" ]]; then
  sudo ln -sfn "${HOME}/.local/bin/uvx" /usr/local/bin/uvx
fi

uv python install 3.12
cd EpistemeOS
uv sync --frozen
