#!/usr/bin/env bash
set -euo pipefail

# Stops and removes the systemd user service created by install.sh
# Run:  ./autostart/ubuntu/uninstall.sh

SERVICE_NAME="insta-post-to-pdf"
SERVICE_FILE="$HOME/.config/systemd/user/${SERVICE_NAME}.service"

systemctl --user disable --now "$SERVICE_NAME" 2>/dev/null || true
rm -f "$SERVICE_FILE"
systemctl --user daemon-reload

echo "Removed the $SERVICE_NAME service and startup entry."
exit 0