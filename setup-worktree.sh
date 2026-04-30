#!/bin/bash
set -e

MAIN_REPO=$(git worktree list | head -1 | awk '{print $1}')

echo "→ Copying config.py from main repo..."
cp "$MAIN_REPO/config.py" ./config.py

echo "→ Creating virtual environment..."
python3 -m venv .venv

echo "→ Installing dependencies..."
.venv/bin/pip install -r requirements.txt

echo "✓ Worktree ready!"
echo ""
echo "  Activate with: source .venv/bin/activate"
