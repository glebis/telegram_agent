#!/bin/bash
# SRS Service Management Script
# Manage launchd jobs for SRS system

SYNC_PLIST=~/Library/LaunchAgents/com.glebkalinin.srs.sync.plist
MORNING_PLIST=~/Library/LaunchAgents/com.glebkalinin.srs.morning.plist

case "$1" in
    start)
        echo "🚀 Starting SRS services..."
        launchctl load "$SYNC_PLIST" 2>/dev/null || echo "  Sync service already loaded"
        launchctl load "$MORNING_PLIST" 2>/dev/null || echo "  Morning service already loaded"
        echo "✅ Services started"
        ;;

    stop)
        echo "🛑 Stopping SRS services..."
        launchctl unload "$SYNC_PLIST" 2>/dev/null || echo "  Sync service not loaded"
        launchctl unload "$MORNING_PLIST" 2>/dev/null || echo "  Morning service not loaded"
        echo "✅ Services stopped"
        ;;

    restart)
        echo "🔄 Restarting SRS services..."
        $0 stop
        sleep 1
        $0 start
        ;;

    status)
        echo "📊 SRS Service Status:"
        echo ""
        echo "Sync (hourly):"
        launchctl list | grep srs.sync || echo "  Not running"
        echo ""
        echo "Morning batch (9am):"
        launchctl list | grep srs.morning || echo "  Not running"
        echo ""
        echo "Logs:"
        echo "  Sync: ~/ai_projects/telegram_agent/logs/srs_sync.log"
        echo "  Morning: ~/ai_projects/telegram_agent/logs/srs_morning.log"
        ;;

    logs)
        echo "📜 Recent SRS logs:"
        echo ""
        echo "=== Sync Log ==="
        tail -20 ~/ai_projects/telegram_agent/logs/srs_sync.log 2>/dev/null || echo "No sync logs yet"
        echo ""
        echo "=== Morning Batch Log ==="
        tail -20 ~/ai_projects/telegram_agent/logs/srs_morning.log 2>/dev/null || echo "No morning logs yet"
        ;;

    test-sync)
        echo "🧪 Testing sync manually..."
        cd ~/ai_projects/telegram_agent/src/services/srs
        ~/ai_projects/telegram_agent/.venv/bin/python3 srs_sync.py -v
        ;;

    test-batch)
        echo "🧪 Testing morning batch manually..."
        ~/ai_projects/telegram_agent/.venv/bin/python3 ~/ai_projects/telegram_agent/scripts/send_morning_batch.py
        ;;

    *)
        echo "SRS Service Manager"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|test-sync|test-batch}"
        echo ""
        echo "Commands:"
        echo "  start       - Start SRS background services"
        echo "  stop        - Stop SRS background services"
        echo "  restart     - Restart SRS background services"
        echo "  status      - Show service status"
        echo "  logs        - Show recent logs"
        echo "  test-sync   - Manually run vault sync"
        echo "  test-batch  - Manually send morning batch"
        exit 1
        ;;
esac
