#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Pulling latest..."
git pull

echo "Restarting service..."
sudo systemctl restart pixel-pi

echo "Done. Logs:"
journalctl -u pixel-pi -n 20 --no-pager
