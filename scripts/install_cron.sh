#!/bin/bash
# Install SRS cron jobs

echo "Installing SRS cron jobs..."

# Create temporary file with current crontab
crontab -l > /tmp/mycron 2>/dev/null || touch /tmp/mycron

# Check if SRS jobs already exist
if grep -q "SRS - Spaced Repetition System" /tmp/mycron; then
    echo "⚠️  SRS cron jobs already installed"
    exit 0
fi

# Add SRS jobs
cat >> /tmp/mycron << 'EOF'

# SRS - Spaced Repetition System for Obsidian vault
# Sync vault to database every hour
0 * * * * cd /Users/server/ai_projects/telegram_agent/src/services/srs && /Users/server/ai_projects/telegram_agent/.venv/bin/python3 srs_sync.py >> /Users/server/ai_projects/telegram_agent/logs/srs_sync.log 2>&1

# Send morning batch at 9am
0 9 * * * /Users/server/ai_projects/telegram_agent/.venv/bin/python3 /Users/server/ai_projects/telegram_agent/scripts/send_morning_batch.py >> /Users/server/ai_projects/telegram_agent/logs/srs_batch.log 2>&1
EOF

# Install new crontab
crontab /tmp/mycron

echo "✅ SRS cron jobs installed"
echo ""
echo "Verify with: crontab -l"
