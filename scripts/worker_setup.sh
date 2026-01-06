#!/bin/bash
# Setup script for the worker queue system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WORKER_PLIST="com.telegram_agent.worker.plist"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"

echo "🔧 Setting up Telegram Agent Worker Queue..."

# Install Python dependencies
echo "📦 Installing Python dependencies..."
cd "$PROJECT_DIR"
source .venv/bin/activate
pip install aiofiles pyyaml python-dotenv aiohttp

# Make worker executable
chmod +x worker_queue.py

# Create log directory
mkdir -p logs

# Install launchd service
echo "🚀 Installing launchd service..."
mkdir -p "$LAUNCHD_DIR"
cp "launchd/$WORKER_PLIST" "$LAUNCHD_DIR/"

# Load service
echo "▶️  Starting worker service..."
launchctl unload "$LAUNCHD_DIR/$WORKER_PLIST" 2>/dev/null || true
launchctl load "$LAUNCHD_DIR/$WORKER_PLIST"

echo ""
echo "✅ Worker queue setup complete!"
echo ""
echo "Service: $WORKER_PLIST"
echo "Status: launchctl list | grep telegram_agent.worker"
echo "Logs: tail -f $PROJECT_DIR/logs/worker.log"
echo ""
echo "Commands:"
echo "  Start:   launchctl start $WORKER_PLIST"
echo "  Stop:    launchctl stop $WORKER_PLIST"
echo "  Restart: launchctl kickstart -k gui/$(id -u)/$WORKER_PLIST"
echo "  Status:  launchctl list | grep worker"
echo ""
