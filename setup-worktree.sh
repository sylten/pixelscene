#!/bin/bash
set -e

MAIN_REPO=$(git worktree list | head -1 | awk '{print $1}')

echo "→ Copying config.py from main repo..."
cp "$MAIN_REPO/config.py" ./config.py

echo "→ Installing dependencies..."
pip install -r requirements.txt

echo "✓ Worktree ready!"
