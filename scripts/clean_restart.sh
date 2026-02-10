#!/usr/bin/env bash
set -euo pipefail

# Clean restart of the Telegram bot production service.
# Kills stale cloudflared tunnels, orphan bot processes, then restarts via launchd.
#
# Usage:
#   ./scripts/clean_restart.sh              # restart production
#   ./scripts/clean_restart.sh --staging    # restart staging

PLIST_PROD="$HOME/Library/LaunchAgents/com.telegram-agent.bot.plist"
PLIST_STAGING="$HOME/Library/LaunchAgents/com.telegram-agent.bot-staging.plist"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"

# Defaults
TARGET="production"
TUNNEL_NAME="telegram-bot"
PLIST="$PLIST_PROD"
PORT=8847

if [[ "${1:-}" == "--staging" ]]; then
    TARGET="staging"
    TUNNEL_NAME="telegram-bot-staging"
    PLIST="$PLIST_STAGING"
    PORT=8848
fi

echo "=== Clean restart: ${TARGET} ==="

# 1. Unload launchd service
echo "[1/5] Unloading launchd service..."
launchctl unload "$PLIST" 2>/dev/null || true
sleep 1

# 2. Kill orphan uvicorn/bot processes on the target port
echo "[2/5] Killing orphan bot processes on port ${PORT}..."
PIDS=$(lsof -ti ":${PORT}" 2>/dev/null || true)
if [[ -n "$PIDS" ]]; then
    echo "  Killing PIDs: $PIDS"
    echo "$PIDS" | xargs kill 2>/dev/null || true
    sleep 1
    # Force-kill any survivors
    PIDS=$(lsof -ti ":${PORT}" 2>/dev/null || true)
    if [[ -n "$PIDS" ]]; then
        echo "  Force-killing survivors: $PIDS"
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
else
    echo "  No orphan processes found"
fi

# 3. Kill stale cloudflared tunnel processes (exact match to avoid cross-target kills)
echo "[3/5] Killing stale cloudflared tunnels for ${TUNNEL_NAME}..."
TUNNEL_PIDS=$(pgrep -f "cloudflared tunnel.*run ${TUNNEL_NAME}$" 2>/dev/null || true)
if [[ -n "$TUNNEL_PIDS" ]]; then
    COUNT=$(echo "$TUNNEL_PIDS" | wc -l | tr -d ' ')
    echo "  Found ${COUNT} stale tunnel process(es)"
    echo "$TUNNEL_PIDS" | xargs kill 2>/dev/null || true
    sleep 2
    # Force-kill any survivors
    TUNNEL_PIDS=$(pgrep -f "cloudflared tunnel.*run ${TUNNEL_NAME}$" 2>/dev/null || true)
    if [[ -n "$TUNNEL_PIDS" ]]; then
        echo "  Force-killing survivors"
        echo "$TUNNEL_PIDS" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
else
    echo "  No stale tunnels found"
fi

# 4. Load launchd service
echo "[4/5] Loading launchd service..."
launchctl load "$PLIST"

# 5. Wait for startup and verify
echo "[5/5] Waiting for bot startup..."
MAX_WAIT=30
ELAPSED=0
while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    HEALTH=$(curl -s --max-time 3 "http://localhost:${PORT}/health" 2>/dev/null || true)
    if echo "$HEALTH" | grep -q '"healthy"'; then
        echo ""
        echo "=== Bot is healthy after ${ELAPSED}s ==="
        echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"

        # Show launchd status
        LABEL=$(basename "$PLIST" .plist)
        echo ""
        echo "Launchd: $(launchctl list | grep "$LABEL" || echo 'not found')"

        # Show tunnel process
        TPID=$(pgrep -f "cloudflared tunnel.*run ${TUNNEL_NAME}$" 2>/dev/null | head -1 || true)
        if [[ -n "$TPID" ]]; then
            echo "Tunnel:  PID ${TPID}"
        else
            echo "Tunnel:  WARNING — no cloudflared process found"
        fi

        # Show last few log lines
        echo ""
        echo "Recent logs:"
        tail -3 "${LOG_DIR}/app.log" 2>/dev/null || true
        exit 0
    fi
    printf "."
done

echo ""
echo "=== FAILED: Bot did not become healthy within ${MAX_WAIT}s ==="
echo ""
echo "Launchd status:"
launchctl list | grep telegram-agent.bot || true
echo ""
echo "Last 10 log lines:"
tail -10 "${LOG_DIR}/app.log" 2>/dev/null || true
echo ""
echo "Stderr:"
tail -10 "${LOG_DIR}/launchd_bot.err" 2>/dev/null || true
exit 1
