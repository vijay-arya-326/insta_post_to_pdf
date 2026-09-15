#!/usr/bin/env bash
set -euo pipefail

# One-step macOS installer:
#   1. Installs uv if it is missing.
#   2. Creates .venv and installs all packages (uv sync).
#   3. Adds a LaunchAgent so the server starts when you sign in.
# Run:  ./autostart/macos/install.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
  elif [[ -x "$HOME/.local/bin/uv" ]]; then
    echo "$HOME/.local/bin/uv"
  elif [[ -x /opt/homebrew/bin/uv ]]; then
    echo /opt/homebrew/bin/uv
  elif [[ -x /usr/local/bin/uv ]]; then
    echo /usr/local/bin/uv
  else
    echo ""
  fi
}

echo "============================================"
echo " Step 1 of 3 - Check/install uv"
echo "============================================"
UV="$(find_uv)"
if [[ -z "$UV" ]]; then
  echo "uv not found. Installing it now..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  UV="$(find_uv)"
fi
if [[ -z "$UV" ]]; then
  echo "Could not install uv. Install it manually from https://docs.astral.sh/uv/ and re-run."
  exit 1
fi
echo "Using uv: $UV"

echo "============================================"
echo " Step 2 of 3 - Create env and install packages"
echo "============================================"
"$UV" sync

echo "============================================"
echo " Step 3 of 3 - Add to startup (LaunchAgent)"
echo "============================================"
"$SCRIPT_DIR/install-autostart.sh"

echo "============================================"
echo " Optional tools check"
echo "============================================"
command -v ffmpeg >/dev/null 2>&1 || echo "NOTE: ffmpeg not found - run: brew install ffmpeg (needed for YouTube MP4/MP3)."
command -v deno >/dev/null 2>&1 || echo "NOTE: deno not found - run: brew install deno (needed for YouTube downloads)."

echo
echo "Done! The server will start when you log in."
echo "Open the app at:  http://127.0.0.1:8585"
echo "To start it right now, run:  $SCRIPT_DIR/start-insta-post-to-pdf.sh"
exit 0