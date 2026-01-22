# SRS Quick Start

Spaced Repetition System for your Obsidian vault via Telegram.

## 🚀 Setup (5 minutes)

```bash
cd ~/ai_projects/telegram_agent
./scripts/srs_setup.sh
```

Follow prompts to:
1. Configure morning batch time (default 9am)
2. Set batch size (default 5 cards)
3. Enter your Telegram chat ID
4. Seed existing evergreen ideas

## 📝 Register Handlers

In `src/main.py`, add:

```python
from src.bot.handlers.srs_handlers import register_srs_handlers

# After creating application:
register_srs_handlers(application)
```

## ⏰ Schedule Background Services (launchd)

LaunchAgents are already installed! Manage them with:

```bash
# Start services
~/ai_projects/telegram_agent/scripts/srs_service.sh start

# Check status
~/ai_projects/telegram_agent/scripts/srs_service.sh status

# View logs
~/ai_projects/telegram_agent/scripts/srs_service.sh logs

# Test manually
~/ai_projects/telegram_agent/scripts/srs_service.sh test-sync
```

Services:
- **Sync** - Runs every hour on the hour
- **Morning batch** - Runs daily at 9am

## 💬 Telegram Commands

- `/review` - Get next 5 cards due for review
- `/review 10` - Get next 10 cards
- `/srs_stats` - View statistics

## 🎯 Rating Buttons

When a card appears:

- **🔄 Again** (0 days → 1 day) - Didn't recall well
- **😓 Hard** (Small increase) - Recalled with effort
- **✅ Good** (Normal increase) - Recalled easily
- **⚡ Easy** (Large increase) - Too easy
- **🔧 Develop** - Open editing session with full context

## 📊 Card Format

```
💡 [Idea Title]

[First 1000 chars...]

...read more in note

🔗 Related:
  • Note 1
  • Note 2

📊 Review #3 | Interval: 7 days

[Buttons]
```

## 🔧 Manual Operations

```bash
cd ~/ai_projects/telegram_agent/src/services/srs

# Sync vault
python3 srs_sync.py -v

# Check due cards
python3 srs_algorithm.py --due --limit 10

# Configure
python3 srs_scheduler.py --config morning_batch_time "08:30"
python3 srs_scheduler.py --config morning_batch_size "7"
```

## 📂 What Gets Reviewed

**Auto-enabled:**
- All evergreen ideas (`Ideas/∞→*.md`)

**Opt-in:**
- Any note with `srs_enabled: true` in frontmatter
- Trails with `srs_next_review` date
- MoCs with `srs_next_review` date

## 🔗 Frontmatter Example

```yaml
---
created_date: '[[20260121]]'
type: idea
tags: [ai-agents]

# SRS fields (auto-added by seed script)
srs_enabled: true
srs_next_review: 2026-02-10
srs_last_review: null
srs_interval: 20
srs_ease_factor: 2.5
srs_repetitions: 0
---
```

## 📖 Full Documentation

- **Integration Guide**: `docs/SRS_INTEGRATION.md`
- **Detailed Docs**: `src/services/srs/README.md`

## ✅ Verification

```bash
# Check database
sqlite3 data/srs/schedule.db "SELECT COUNT(*) FROM srs_cards;"

# Test review command
# In Telegram: /review

# Check logs
tail -f telegram_agent.log
```

## 🎯 Next: Develop Button Integration

The "Develop" button currently shows a prompt. To fully integrate with Agent SDK, update `src/bot/handlers/srs_handlers.py` to start a claude_code session (see integration guide).
