#!/bin/bash
# Control script for worker queue service

WORKER_PLIST="com.telegram_agent.worker"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

case "$1" in
    start)
        echo "▶️  Starting worker..."
        launchctl start "$WORKER_PLIST"
        ;;
    stop)
        echo "⏸️  Stopping worker..."
        launchctl stop "$WORKER_PLIST"
        ;;
    restart)
        echo "🔄 Restarting worker..."
        launchctl kickstart -k "gui/$(id -u)/$WORKER_PLIST"
        ;;
    status)
        echo "📊 Worker status:"
        launchctl list | grep -i worker || echo "Worker not running"
        echo ""
        echo "📋 Queue status:"
        python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
from src.services.job_queue_service import JobQueueService
jq = JobQueueService()
status = jq.get_queue_status()
print(f'Pending: {status[\"pending\"]}')
print(f'In Progress: {status[\"in_progress\"]}')
print(f'Completed: {status[\"completed\"]}')
print(f'Failed: {status[\"failed\"]}')
"
        ;;
    logs)
        tail -f "$PROJECT_DIR/logs/worker.log"
        ;;
    test)
        echo "🧪 Running test job..."
        python3 "$PROJECT_DIR/worker_queue.py" --once
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|test}"
        exit 1
        ;;
esac
