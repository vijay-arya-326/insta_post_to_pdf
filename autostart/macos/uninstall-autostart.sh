#!/usr/bin/env bash
set -euo pipefail

LABEL="com.local.insta-post-to-pdf"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ -f "$DEST" ]]; then
  launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
  rm -f "$DEST"
  echo "Removed the LaunchAgent."
else
  echo "No LaunchAgent was found."
fi
