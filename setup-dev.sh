#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== pixelscene dev setup ==="
echo "Repo: $REPO_DIR"
echo ""

# ── Python virtual environment ───────────────────────────────────────────────
echo "→ Creating virtual environment..."
python3 -m venv "$REPO_DIR/.venv"

echo "→ Installing pip packages..."
"$REPO_DIR/.venv/bin/pip" install --upgrade pip -q
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
echo "  ✓ Pip packages installed"

# ── config.py ────────────────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/config.py" ]; then
    if [ -f "$REPO_DIR/config.example.py" ]; then
        cp "$REPO_DIR/config.example.py" "$REPO_DIR/config.py"
        echo "  ✓ config.py created from example"
    else
        echo "  ⚠ No config.py found. Create it manually before running."
    fi
else
    echo "  ✓ config.py already exists"
fi

echo ""
echo "=== Setup complete ==="
echo "  Run the scene:"
echo "    source .venv/bin/activate && python3 main.py"
echo "  Or without activating:"
echo "    .venv/bin/python3 main.py"
