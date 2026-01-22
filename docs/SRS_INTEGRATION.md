# SRS Integration Guide

Spaced Repetition System integration for telegram_agent.

## Quick Start

```bash
# Setup (5 minutes)
cd ~/ai_projects/telegram_agent
./scripts/srs_setup.sh

# Start services
~/ai_projects/telegram_agent/scripts/srs_service.sh start

# Telegram commands
/review          # Get next 5 cards due for review
/review 10       # Get next 10 cards
/srs_stats       # View statistics
```

## Overview

The SRS system resurfaces ideas from your Obsidian vault using spaced repetition (SM-2 algorithm). Cards are sent via Telegram with rating buttons and a "Develop" button that launches Agent SDK sessions.

## Architecture

```
Obsidian Vault (frontmatter)
    ↓ sync
SQLite DB (data/srs/schedule.db)
    ↓ query
Scheduler (scripts/send_morning_batch.py)
    ↓ send
Telegram Bot (handlers/srs_handlers.py)
    ↓ callbacks
SRS Service (services/srs_service.py)
    ↓ develop
Agent SDK Session
```

## Setup

### 1. Run Setup Script

```bash
cd ~/ai_projects/telegram_agent
./scripts/srs_setup.sh
```

This will:
- Create database
- Configure settings (batch time, batch size, chat ID)
- Seed existing evergreen ideas
- Sync vault to database

### 2. Register Handlers

In `src/main.py`, add:

```python
from src.bot.handlers.srs_handlers import register_srs_handlers

# In your main() function, after creating application:
register_srs_handlers(application)
```

### 3. Schedule Background Services (launchd)

LaunchAgents are installed by the setup script. Manage them with:

```bash
# Start services
~/ai_projects/telegram_agent/scripts/srs_service.sh start

# Check status
~/ai_projects/telegram_agent/scripts/srs_service.sh status

# View logs
~/ai_projects/telegram_agent/scripts/srs_service.sh logs

# Test manually
~/ai_projects/telegram_agent/scripts/srs_service.sh test-sync
~/ai_projects/telegram_agent/scripts/srs_service.sh test-batch
```

Services:
- **Vault Sync** - Runs every hour on the hour
- **Morning Batch** - Runs daily at 9am (configurable)

## Usage

### Commands

**`/review [N]`**
- Shows next N cards due for review (default 5, max 20)
- Cards appear with rating buttons

**`/srs_stats`**
- Shows statistics about your SRS cards
- Total, due now, avg ease, avg interval by type

### Rating Buttons

- **🔄 Again** - Restart interval (1 day)
- **😓 Hard** - Slight increase, lower ease
- **✅ Good** - Normal increase (interval × ease)
- **⚡ Easy** - Large increase, higher ease

### Develop Button

**🔧 Develop** - Opens development session with:
- Full note content
- Backlinks (2 levels deep)
- Context for editing/expanding the idea

Currently shows a prompt to start working. To fully integrate with Agent SDK:

```python
# In srs_handlers.py, srs_callback_handler function:

if result.get('action') == 'develop':
    dev_context = srs_service.get_develop_context(note_path)

    # Start Agent SDK session
    from src.services.claude_code_service import claude_code_service

    session_id = await claude_code_service.start_session(
        update.effective_chat.id,
        initial_prompt=dev_context['context_prompt'],
        working_directory=str(Path(dev_context['vault_path']).parent)
    )

    await query.message.reply_text(
        f"🔧 Development session started!\n\n"
        f"Session: {session_id}\n"
        f"Working on: {Path(note_path).stem}"
    )
```

## Frontmatter Format

### Evergreen Ideas (Auto-enabled)

```yaml
---
created_date: '[[20260121]]'
type: idea
tags: [knowledge-work]

# SRS fields (added by srs_seed.py)
srs_enabled: true
srs_next_review: 2026-02-15
srs_last_review: null
srs_interval: 25
srs_ease_factor: 2.5
srs_repetitions: 0
---
```

### Other Notes (Opt-in)

Add to any note to enable SRS:

```yaml
---
srs_enabled: true
srs_next_review: 2026-01-25
srs_interval: 4
srs_ease_factor: 2.5
srs_repetitions: 1
---
```

## Morning Batch

- Configured via database (see Setup)
- Default: 9am, 5 cards
- Only sends once per day
- Requires `telegram_chat_id` in config

## Database

Location: `data/srs/schedule.db`

### Useful Queries

**Cards due now:**
```sql
SELECT title, note_path, next_review_date
FROM srs_cards
WHERE is_due = 1 AND srs_enabled = 1;
```

**Review history:**
```sql
SELECT c.title, h.reviewed_at, h.rating, h.interval_after
FROM review_history h
JOIN srs_cards c ON h.card_id = c.id
ORDER BY h.reviewed_at DESC
LIMIT 20;
```

**Stats by type:**
```sql
SELECT
    note_type,
    COUNT(*) as total,
    AVG(ease_factor) as avg_ease,
    AVG(interval_days) as avg_interval
FROM srs_cards
WHERE srs_enabled = 1
GROUP BY note_type;
```

## Manual Operations

### Sync Vault

```bash
cd ~/ai_projects/telegram_agent/src/services/srs
python3 srs_sync.py -v
```

### Check Due Cards

```bash
python3 srs_algorithm.py --due --limit 10
```

### Test Scheduler

```bash
python3 srs_scheduler.py --review 5
```

### Configure Settings

```bash
# Set morning batch time
python3 srs_scheduler.py --config morning_batch_time "08:30"

# Set batch size
python3 srs_scheduler.py --config morning_batch_size "7"

# Set chat ID
python3 srs_scheduler.py --config telegram_chat_id "123456789"
```

## Files

```
telegram_agent/
├── data/srs/
│   ├── schedule.db          # SQLite database
│   └── schema.sql           # Database schema
├── src/
│   ├── bot/handlers/
│   │   └── srs_handlers.py  # Command handlers
│   └── services/
│       ├── srs_service.py   # Main service
│       └── srs/
│           ├── __init__.py
│           ├── srs_algorithm.py   # SM-2 implementation
│           ├── srs_scheduler.py   # Batch scheduling
│           ├── srs_seed.py        # Initial seeding
│           ├── srs_sync.py        # Vault sync
│           ├── srs_telegram.py    # Telegram utils
│           └── README.md          # Detailed docs
└── scripts/
    ├── srs_setup.sh               # Setup wizard
    └── send_morning_batch.py      # Cron script
```

## Troubleshooting

### Cards not appearing

1. Check database:
   ```bash
   sqlite3 data/srs/schedule.db "SELECT COUNT(*) FROM srs_cards WHERE is_due = 1;"
   ```

2. Verify frontmatter has `srs_enabled: true`

3. Re-sync vault:
   ```bash
   cd src/services/srs && python3 srs_sync.py -v
   ```

### Morning batch not sending

1. Check services are running:
   ```bash
   ~/ai_projects/telegram_agent/scripts/srs_service.sh status
   ```

2. Check logs:
   ```bash
   ~/ai_projects/telegram_agent/scripts/srs_service.sh logs
   ```

3. Test manually:
   ```bash
   ~/ai_projects/telegram_agent/scripts/srs_service.sh test-batch
   ```

4. Verify `telegram_chat_id` is configured:
   ```bash
   cd src/services/srs
   python3 -c "from srs_scheduler import get_config; print(get_config('telegram_chat_id'))"
   ```

### Handlers not working

1. Ensure handlers are registered in `main.py`

2. Check bot logs for errors

3. Verify callback query pattern matches: `^srs_`

## Next Steps

- [ ] Integrate "Develop" button with Agent SDK fully
- [ ] Add analytics dashboard
- [ ] Support for suspending/resuming cards
- [ ] Tag-based filtering for review sessions
- [ ] Custom difficulty presets per note type
