#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
START="$SCRIPT_DIR/start-insta-post-to-pdf.sh"
TEMPLATE="$SCRIPT_DIR/com.local.insta-post-to-pdf.plist"
LABEL="com.local.insta-post-to-pdf"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

chmod +x "$START"
mkdir -p "$HOME/Library/LaunchAgents"

sed \
  -e "s|__WORKING_DIRECTORY__|${ROOT}|g" \
  -e "s|__START_SCRIPT__|${START}|g" \
  "$TEMPLATE" > "$DEST"

launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"

echo "Installed LaunchAgent. The server will start when you sign in."
echo "App URL: http://127.0.0.1:8585"
