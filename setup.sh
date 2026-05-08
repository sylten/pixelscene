#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== pixelscene deployment setup ==="
echo "Repo: $REPO_DIR"
echo ""

# ── Python virtual environment ──────────────────────────────────────────────
echo "→ Creating virtual environment..."
python3 -m venv "$REPO_DIR/.venv"

echo "→ Installing dependencies..."
"$REPO_DIR/.venv/bin/pip" install --upgrade pip -q
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
echo "  ✓ Dependencies installed"

# ── config.py ───────────────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/config.py" ]; then
    if [ -f "$REPO_DIR/config.example.py" ]; then
        cp "$REPO_DIR/config.example.py" "$REPO_DIR/config.py"
        echo "  ✓ config.py created from example — edit it before starting"
    else
        echo "  ⚠ No config.py found and no config.example.py to copy from."
        echo "    Create config.py manually before running the app."
    fi
else
    echo "  ✓ config.py already exists"
fi

# ── systemd service ──────────────────────────────────────────────────────────
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
