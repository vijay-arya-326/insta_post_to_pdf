#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV="${HOME}/.local/bin/uv"
elif [[ -x /opt/homebrew/bin/uv ]]; then
  UV=/opt/homebrew/bin/uv
elif [[ -x /usr/local/bin/uv ]]; then
  UV=/usr/local/bin/uv
else
  echo "uv was not found. Install uv and try again." >&2
  exit 1
fi

exec "$UV" run uvicorn app:app --host 127.0.0.1 --port 8585
