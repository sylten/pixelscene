#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== pixelscene deployment setup ==="
echo "Repo: $REPO_DIR"
echo ""

# ── System packages (apt) ────────────────────────────────────────────────────
# pygame has no pre-built pip wheel for Raspberry Pi, so install it and other
# heavy deps via apt. Flask needs >= 3.0 which apt usually doesn't have, so
# that goes through pip.
if command -v apt &>/dev/null; then
    echo "→ Installing system packages via apt..."
    sudo apt install -y \
        python3-pygame \
        python3-pil \
        python3-numpy
    echo "  ✓ System packages installed"
    VENV_EXTRA="--system-site-packages"
else
    echo "  (apt not found — skipping system packages, pip will build from source)"
    VENV_EXTRA=""
fi

# ── Python virtual environment ───────────────────────────────────────────────
echo "→ Creating virtual environment..."
python3 -m venv $VENV_EXTRA "$REPO_DIR/.venv"

echo "→ Installing pip packages..."
"$REPO_DIR/.venv/bin/pip" install --upgrade pip -q
if [ -n "$VENV_EXTRA" ]; then
    # apt covers pygame, Pillow, numpy — only need Flask
    "$REPO_DIR/.venv/bin/pip" install "flask>=3.0"
else
    "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
fi
echo "  ✓ Pip packages installed"

# ── config.py ────────────────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/config.py" ]; then
    if [ -f "$REPO_DIR/config.example.py" ]; then
        cp "$REPO_DIR/config.example.py" "$REPO_DIR/config.py"
        echo "  ✓ config.py created from example — edit it before starting"
    else
        echo "  ⚠ No config.py found. Create it manually before running the app."
    fi
else
    echo "  ✓ config.py already exists"
fi

# ── systemd service ───────────────────────────────────────────────────────────
SERVICE_NAME="pixel-pi"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

if [ ! -f "$SERVICE_FILE" ]; then
    echo ""
    echo "→ Installing systemd service ($SERVICE_NAME)..."
    CURRENT_USER="$(whoami)"

    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Pixelscene renderer
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$REPO_DIR
ExecStart=$REPO_DIR/.venv/bin/python3 $REPO_DIR/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    echo "  ✓ Service installed and enabled"
    echo "  Start it now with: sudo systemctl start $SERVICE_NAME"
else
    echo "  ✓ systemd service already installed"
fi

echo ""
echo "=== Setup complete ==="
echo "  Pull latest + restart: ./restart.sh"
