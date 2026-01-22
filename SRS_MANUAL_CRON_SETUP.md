# Manual Cron Setup for SRS

Automated cron installation didn't work via scripts. Here's how to add manually:

## Run:

```bash
crontab -e
```

## Add these lines:

```cron
# SRS - Spaced Repetition System for Obsidian vault
# Sync vault to database every hour
0 * * * * cd /Users/server/ai_projects/telegram_agent/src/services/srs && /Users/server/ai_projects/telegram_agent/.venv/bin/python3 srs_sync.py >> /Users/server/ai_projects/telegram_agent/logs/srs_sync.log 2>&1

# Send morning batch at 9am
0 9 * * * /Users/server/ai_projects/telegram_agent/.venv/bin/python3 /Users/server/ai_projects/telegram_agent/scripts/send_morning_batch.py >> /Users/server/ai_projects/telegram_agent/logs/srs_batch.log 2>&1
```

## Verify:

```bash
crontab -l | grep SRS
```

## Alternative: Test manually without cron

```bash
# Sync now
cd /Users/server/ai_projects/telegram_agent/src/services/srs
source /Users/server/ai_projects/telegram_agent/.venv/bin/activate
python3 srs_sync.py

# Send batch now (requires telegram_chat_id configured)
python3 /Users/server/ai_projects/telegram_agent/scripts/send_morning_batch.py
```
