# Spaced Repetition System (SRS) for Obsidian Vault

A vault-native spaced repetition system that resurfaces ideas via Telegram using the SM-2 algorithm.

## System Architecture

```
┌─────────────────┐
│ Obsidian Vault  │
│  (frontmatter)  │
└────────┬────────┘
         │
         │ sync
         ▼
┌─────────────────┐      ┌──────────────┐
│  SQLite DB      │◄─────┤  Scheduler   │
│  (schedule.db)  │      │  (cron/hourly)│
└────────┬────────┘      └──────────────┘
         │
         │ query due cards
         ▼
┌─────────────────┐      ┌──────────────┐
│ Telegram Bot    │◄─────┤ User Ratings │
│  (send cards)   │      │ (buttons)    │
└─────────────────┘      └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ Agent SDK    │
                         │ (develop)    │
                         └──────────────┘
```

## Components

### 1. Database (`/Volumes/LaCie/DataLake/srs/schedule.db`)
- **srs_cards**: Card metadata and scheduling state
- **review_history**: Review logs for analytics
- **srs_config**: System configuration

### 2. Scripts (`/Users/server/Research/vault/scripts/`)

#### `srs_seed.py` - Initial Setup
Seeds SRS metadata to existing evergreen ideas.

```bash
# Preview changes
python3 srs_seed.py --dry-run

# Seed all evergreen ideas
python3 srs_seed.py
```

Adds to frontmatter:
```yaml
srs_enabled: true
srs_next_review: 2026-01-22
srs_last_review: null
srs_interval: 7
srs_ease_factor: 2.5
srs_repetitions: 0
```

#### `srs_sync.py` - Vault Synchronization
Syncs vault frontmatter to database.

```bash
# Sync all notes
python3 srs_sync.py

# Verbose output
python3 srs_sync.py -v
```

Run hourly via cron:
```cron
0 * * * * cd /Users/server/Research/vault/scripts && python3 srs_sync.py
```

#### `srs_algorithm.py` - SM-2 Implementation
Core algorithm for calculating review intervals.

```bash
# Show due cards
python3 srs_algorithm.py --due --limit 10
```

**Rating Scale:**
- 0 (Again): Restart interval at 1 day
- 1 (Hard): Slightly increase interval, decrease ease
- 2 (Good): Normal increase (interval × ease_factor)
- 3 (Easy): Large increase, increase ease

**Intervals:**
- First review: 1 day
- Second review: 3 days
- Subsequent: previous_interval × ease_factor

#### `srs_scheduler.py` - Scheduling Service
Manages morning batches and on-demand reviews.

```bash
# Configure morning batch time
python3 srs_scheduler.py --config morning_batch_time "09:00"
python3 srs_scheduler.py --config morning_batch_size "5"

# Send morning batch (if due)
python3 srs_scheduler.py --batch

# Get cards for /review command
python3 srs_scheduler.py --review 5
```

#### `srs_telegram.py` - Telegram Integration
Bot handlers for card presentation and ratings.

```python
from srs_telegram import (
    send_morning_batch_to_telegram,
    handle_review_command,
    handle_rating_callback,
    get_develop_context
)
```

## Setup Instructions

### 1. Seed Existing Ideas

```bash
cd /Users/server/Research/vault/scripts

# Preview
python3 srs_seed.py --dry-run

# Seed
python3 srs_seed.py
```

### 2. Initial Sync

```bash
python3 srs_sync.py -v
```

### 3. Configure System

```bash
# Set morning batch time (24-hour format)
python3 srs_scheduler.py --config morning_batch_time "09:00"

# Set batch size
python3 srs_scheduler.py --config morning_batch_size "5"

# Set your Telegram chat ID
python3 srs_scheduler.py --config telegram_chat_id "YOUR_CHAT_ID"
```

### 4. Schedule Cron Jobs

Add to crontab (`crontab -e`):

```cron
# Sync vault every hour
0 * * * * cd /Users/server/Research/vault/scripts && python3 srs_sync.py

# Send morning batch at 9am (check happens in script)
0 9 * * * cd /Users/server/Research/vault/scripts && python3 srs_scheduler.py --batch
```

### 5. Integrate with Telegram Bot

In your main bot file:

```python
from srs_telegram import (
    send_morning_batch_to_telegram,
    handle_review_command,
    handle_rating_callback,
    get_develop_context
)

# /review command
@bot.message_handler(commands=['review'])
def review_command(message):
    count = handle_review_command(bot.send_message, message.chat.id, limit=5)
    if count > 0:
        bot.send_message(message.chat.id, f"📬 Sent {count} cards")

# Rating button callbacks
@bot.callback_query_handler(func=lambda call: call.data.startswith('srs_'))
def rating_callback(call):
    result = handle_rating_callback(call.data)

    if not result['success']:
        bot.answer_callback_query(call.id, f"❌ {result['error']}")
        return

    if result['action'] == 'develop':
        # Launch Agent SDK session
        context = get_develop_context(result['note_path'])
        # Start multi-turn conversation
        start_agent_sdk_session(
            call.message.chat.id,
            context['context_prompt'],
            context_note_path=result['note_path']
        )
        bot.answer_callback_query(call.id, "🔧 Opening development session...")
    else:
        # Show rating confirmation
        bot.edit_message_text(
            result['message'],
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, "✅ Scheduled!")
```

## Usage

### Card Format in Telegram

```
💡 [Note Title]

[First 1000 chars of content]

...read more in note

🔗 Related:
  • Note 1
  • Note 2
  • Note 3

📊 Review #3 | Interval: 7 days

[🔄 Again] [😓 Hard] [✅ Good] [⚡ Easy]
[🔧 Develop]
```

### Morning Batch
- Sends at configured time (default 9am)
- Sends configured number of cards (default 5)
- Only sends once per day

### On-Demand Review
- Use `/review` command in Telegram
- Gets next 5 due cards
- Can be called anytime

### Develop Button
- Opens Agent SDK session with note context
- Full note content + backlinks provided
- Multi-turn conversation enabled
- Can edit note, create related notes, explore connections

## Frontmatter Structure

### For Evergreen Ideas
```yaml
---
created_date: '[[20260110]]'
type: idea
tags: [ai-agents, knowledge-work]

# SRS fields
srs_enabled: true
srs_next_review: 2026-01-22
srs_last_review: 2026-01-21
srs_interval: 7
srs_ease_factor: 2.5
srs_repetitions: 3
---
```

### For Trails/MoCs (Optional SRS)
```yaml
---
type: trail
status: active
next_review: 2026-01-15  # Existing field, monthly cadence
# OR enable SM-2 for trails:
srs_enabled: true
srs_next_review: 2026-01-22
# ... rest of SRS fields
---
```

## SM-2 Algorithm Details

### Ease Factor Adjustment
```
EF' = EF + (0.1 - (3-q) * (0.08 + (3-q) * 0.02))
```

Where `q` is rating (0-3).

### Interval Calculation
- **First**: 1 day
- **Second**: 3 days
- **N-th**: previous_interval × ease_factor

### Minimum Values
- Ease factor: 1.3 (never goes below)
- Interval: 1 day (on "Again")

## Database Queries

### Check due cards
```sql
SELECT title, next_review_date, interval_days
FROM srs_cards
WHERE srs_enabled = 1 AND next_review_date <= date('now')
ORDER BY next_review_date
LIMIT 10;
```

### Review statistics
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

### Review history
```sql
SELECT
    c.title,
    h.reviewed_at,
    h.rating,
    h.interval_after
FROM review_history h
JOIN srs_cards c ON h.card_id = c.id
ORDER BY h.reviewed_at DESC
LIMIT 20;
```

## Maintenance

### Re-sync all notes
```bash
python3 srs_sync.py -v
```

### Reset a card
```sql
UPDATE srs_cards
SET
    interval_days = 1,
    ease_factor = 2.5,
    repetitions = 0,
    next_review_date = date('now', '+1 day')
WHERE note_path = 'Ideas/∞→Your Note.md';
```

### Disable SRS for a note
In frontmatter:
```yaml
srs_enabled: false
```

Then sync:
```bash
python3 srs_sync.py
```

## Troubleshooting

### Cards not appearing
1. Check database: `sqlite3 /Volumes/LaCie/DataLake/srs/schedule.db`
2. Run: `SELECT COUNT(*) FROM srs_cards WHERE is_due = 1;`
3. Verify frontmatter has `srs_enabled: true`
4. Re-sync: `python3 srs_sync.py -v`

### Morning batch not sending
1. Check last batch time:
   ```sql
   SELECT value FROM srs_config WHERE key = 'last_batch_sent';
   ```
2. Check cron is running: `crontab -l`
3. Check cron logs: Check system logs for cron output

### Develop button not working
- Ensure Agent SDK session handler is implemented in bot
- Check `get_develop_context()` returns proper context
- Verify note path is accessible

## Future Enhancements

- [ ] Analytics dashboard
- [ ] Mobile app for reviews
- [ ] Custom difficulty presets per note type
- [ ] Lapsed card recovery workflow
- [ ] Suspend/unsuspend cards
- [ ] Tag-based filtering for reviews
- [ ] Learning statistics over time
