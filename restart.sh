#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Pulling latest..."
git pull

echo "Restarting service..."
sudo systemctl restart pixel-pi

echo ""
echo "=== pixel-pi logs ==="
journalctl -u pixel-pi -n 30 --no-pager

echo ""
echo "=== fbcp status ==="
sudo systemctl status fbcp --no-pager || true
