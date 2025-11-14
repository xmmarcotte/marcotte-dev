#!/bin/bash
#
# Setup Memory Janitor systemd service and timer
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🧹 Setting up Memory Janitor..."

# Copy systemd files
sudo cp "$PROJECT_ROOT/services/spot-mcp-server/memory-janitor.service" /etc/systemd/system/
sudo cp "$PROJECT_ROOT/services/spot-mcp-server/memory-janitor.timer" /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start timer
sudo systemctl enable memory-janitor.timer
sudo systemctl start memory-janitor.timer

# Show status
sudo systemctl status memory-janitor.timer --no-pager

echo ""
echo "✅ Memory Janitor configured!"
echo ""
echo "📊 Commands:"
echo "  Status:  sudo systemctl status memory-janitor.timer"
echo "  Logs:    sudo journalctl -u memory-janitor.service -f"
echo "  Run now: sudo systemctl start memory-janitor.service"
echo "  Disable: sudo systemctl stop memory-janitor.timer && sudo systemctl disable memory-janitor.timer"
