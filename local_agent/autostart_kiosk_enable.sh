#!/usr/bin/env bash
# Enables Chromium kiosk-mode autostart (Raspberry Pi OS desktop) pointed at the local status page.
set -euo pipefail

KIOSK_URL="${KIOSK_URL:-http://localhost:8787}"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/mcode-kiosk.desktop"

BROWSER_BIN=$(command -v chromium-browser || command -v chromium || true)
if [ -z "$BROWSER_BIN" ]; then
    echo "chromium-browser/chromium not found; install it first: sudo apt-get install -y chromium-browser" >&2
    exit 1
fi

mkdir -p "$AUTOSTART_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Meet Code Kiosk
Exec=$BROWSER_BIN --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --incognito "$KIOSK_URL"
X-GNOME-Autostart-enabled=true
EOF

echo "Kiosk autostart enabled: $DESKTOP_FILE"
echo "Will launch $BROWSER_BIN in kiosk mode at $KIOSK_URL on next desktop login/reboot."
