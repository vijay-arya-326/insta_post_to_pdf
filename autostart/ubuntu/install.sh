#!/usr/bin/env bash
set -euo pipefail

# One-step Ubuntu installer:
#   1. Installs uv if it is missing.
#   2. Creates .venv and installs all packages (uv sync).
#   3. Adds a systemd user service so the server starts when you log in.
# Run:  ./autostart/ubuntu/install.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICE_NAME="insta-post-to-pdf"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/${SERVICE_NAME}.service"

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
  elif [[ -x "$HOME/.local/bin/uv" ]]; then
    echo "$HOME/.local/bin/uv"
  elif [[ -x /usr/bin/uv ]]; then
    echo /usr/bin/uv
  elif [[ -x /usr/local/bin/uv ]]; then
    echo /usr/local/bin/uv
  else
    echo ""
  fi
}

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemd not found on this system - the startup step needs systemd."
  exit 1
fi

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
mkdir -p "$SERVICE_DIR"

echo "============================================"
echo " Step 3 of 3 - Add to startup (systemd user service)"
echo "============================================"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Instagram post to PDF
After=network.target

[Service]
WorkingDirectory=$ROOT
ExecStart=$UV run uvicorn app:app --host 127.0.0.1 --port 8585
Restart=on-failure

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

echo "============================================"
echo " Optional tools check"
echo "============================================"
command -v ffmpeg >/dev/null 2>&1 || echo "NOTE: ffmpeg not found - run: sudo apt install ffmpeg (needed for YouTube MP4/MP3)."
command -v deno >/dev/null 2>&1 || echo "NOTE: deno not found - run: curl -fsSL https://deno.land/install.sh | sh (needed for YouTube downloads)."

echo
echo "Done! The server is running now and starts on login."
echo "Open the app at:  http://127.0.0.1:8585"
exit 0