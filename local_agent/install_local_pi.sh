#!/usr/bin/env bash
# Poetry-free install for the local print agent (e.g. Raspberry Pi with Python 3.9.2,
# where pyproject.toml's `python = "^3.11"` constraint rules out a poetry/editable install).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
VENV_DIR="local_agent/.venv"
PYTHON=${PYTHON:-python3}

echo "==> Installing system packages"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip libusb-1.0-0 libjpeg-dev zlib1g-dev

echo "==> Creating virtualenv at $VENV_DIR"
"$PYTHON" -m venv "$VENV_DIR"

echo "==> Installing Python dependencies"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install \
    "qrcode>=7.4,<8" \
    "pillow>=10.1,<11" \
    "requests>=2.31,<3" \
    "brother_ql>=0.9,<0.10" \
    "pyusb>=1.2,<2" \
    "python-dotenv>=1.0,<2" \
    "pymupdf>=1.24,<2"

if [ ! -f local_agent/.env ]; then
    echo "==> Creating local_agent/.env from example (edit it before starting!)"
    cp local_agent/.env.example local_agent/.env
fi

echo "==> Installing udev rule for USB printer access"
sudo tee /etc/udev/rules.d/99-brother-ql.rules > /dev/null <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="04f9", MODE="0666"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "==> Installing systemd service"
sed "s#__WORKDIR__#$REPO_ROOT#g; s#__VENV_PY__#$REPO_ROOT/$VENV_DIR/bin/python#g" \
    local_agent/mcode-agent.service | sudo tee /etc/systemd/system/mcode-agent.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now mcode-agent

echo "Done. Edit local_agent/.env, then: sudo systemctl restart mcode-agent"
echo "Logs: journalctl -u mcode-agent -f"
