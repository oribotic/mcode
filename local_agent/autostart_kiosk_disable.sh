#!/usr/bin/env bash
# Disables the Chromium kiosk-mode autostart added by autostart_kiosk_enable.sh.
set -euo pipefail

DESKTOP_FILE="$HOME/.config/autostart/mcode-kiosk.desktop"

if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "Kiosk autostart disabled (removed $DESKTOP_FILE)."
else
    echo "Kiosk autostart was not enabled (no $DESKTOP_FILE found)."
fi
