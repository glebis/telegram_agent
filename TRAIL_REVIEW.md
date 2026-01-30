# Trail Review System

Automated trail progress tracking via scheduled Telegram polls.

## Overview

The trail review system sends interactive polls throughout the day to check in on your active trails. It helps maintain awareness of project progress and keeps trail metadata up to date.

## Features

- **Scheduled Polls**: 3 daily check-ins (configurable times)
- **Multi-Question Sequence**: Velocity → Status → Stage → Next Review
- **Smart Selection**: Prioritizes overdue trails
- **Auto-Update**: Poll answers update trail frontmatter automatically
- **Manual Reviews**: `/trail` commands for on-demand reviews

## Configuration

### Environment Variables

Add to `.env` or `.env.local`:

```bash
# Enable/disable trail review scheduler
TRAIL_REVIEW_ENABLED=true

# Your Telegram chat ID (required for scheduled reviews)
TRAIL_REVIEW_CHAT_ID=123456789

# Poll times (24-hour format, comma-separated)
# Default: 09:00,14:00,20:00
TRAIL_REVIEW_TIMES=09:00,14:00,20:00
```

### Getting Your Chat ID

1. Send a message to your bot
2. Check logs for `chat_id` in incoming messages
3. Or use: https://t.me/userinfobot

## Usage

### Scheduled Reviews

Once configured, the bot will automatically send trail review polls at your specified times. It selects trails based on:

1. **Overdue reviews** (past `next_review` date)
2. **Active trails** without scheduled reviews
3. **Random selection** from active trails

### Manual Commands

#### `/trail` or `/trail:status`
Start review for the most urgent trail.

```
/trail
```

#### `/trail:list`
Show all trails due for review with urgency indicators.

```
/trail:list
```

Output:
```
📋 Trails Due for Review

🔴 Agentic Knowledge Work
   🔥 high · active
   Due: 2026-01-08 (19 days overdue)

🟡 Voice Claude
   ⚡ medium · active
   Due: 2026-01-20 (7 days overdue)

🟢 Personal OS
   🐢 low · paused
   No review scheduled
```

#### `/trail:review <name>`
Review a specific trail by name (partial match supported).

```
/trail:review Voice Claude
```

### Poll Flow

When a trail review starts, you'll receive a sequence of 4 polls:

#### 1. Velocity
```
🚀 Trail velocity for 'Agentic Knowledge Work'?

○ 🔥 High (moving fast)
○ ⚡ Medium (steady progress)
○ 🐢 Low (slow/background)
○ ⏸️ Paused
```

#### 2. Status
```
📊 Status for 'Agentic Knowledge Work'?

○ ✅ Active (working on it)
○ ⏸️ Paused (on hold)
○ 🎯 Completed
○ ❌ Abandoned
```

#### 3. Stage
```
🔬 Research stage for 'Agentic Knowledge Work'?

○ 🔍 Exploring
○ 📚 Synthesizing
○ 🔗 Integrating
○ 💡 Applying
```

*Stage options vary by trail direction (research/building/learning)*

#### 4. Next Review
```
📅 When to review 'Agentic Knowledge Work' again?

○ 🔔 Tomorrow (urgent)
○ 📆 In 1 week
○ 📆 In 2 weeks
○ 📆 In 1 month
```

### Review Summary

After answering all polls, you'll receive a summary:

```
✅ Trail Review Complete: Agentic Knowledge Work

Updates:
• velocity → high
• status → active
• next_review → 2026-02-03
• last_updated → 2026-01-27
```

## Trail File Format

The system reads and updates trail frontmatter:

```yaml
---
type: trail
status: active              # Updated by polls
velocity: high              # Updated by polls
next_review: 2026-02-03     # Updated by polls
last_updated: 2026-01-27    # Auto-updated
direction: building         # Determines stage options
---
```

## Architecture

### Components

1. **`trail_review_service.py`** - Core logic for trail selection, poll creation, and file updates
2. **`trail_handlers.py`** - Telegram handlers for commands and poll answers
3. **`trail_scheduler.py`** - Scheduled job configuration
4. **Bot initialization** - Registers handlers and scheduler

### Data Flow

```
Scheduled Time → send_scheduled_trail_review()
                        ↓
                get_random_active_trail()
                        ↓
                start_poll_sequence()
                        ↓
User answers → handle_trail_poll_answer()
                        ↓
                get_next_poll() (repeat)
                        ↓
All answered → finalize_review()
                        ↓
                Update trail file frontmatter
```

### Poll State Management

Polls are tracked in `context.bot_data['trail_polls']`:

```python
{
    'poll_id_abc123': {
        'trail_path': '/path/to/Trail - Name.md',
        'field': 'velocity',
        'chat_id': 123456789
    }
}
```

This allows the bot to match poll answers back to the correct trail and field.

## Integration with SRS

The trail review system complements the existing SRS (Spaced Repetition System):

- **SRS**: Reviews individual ideas/notes from vault
- **Trail Review**: Reviews project/research progress

Both use similar patterns:
- Scheduled reviews
- Poll-based interaction
- Frontmatter updates
- Spaced repetition logic

## Troubleshooting

### No polls received

1. Check `TRAIL_REVIEW_ENABLED=true`
2. Verify `TRAIL_REVIEW_CHAT_ID` is set and correct
3. Ensure trails exist in `~/Research/vault/Trails/`
4. Check trails have `type: trail` in frontmatter
5. Verify bot logs for scheduler initialization

### Polls don't update files

1. Check file permissions on vault directory
2. Verify frontmatter format (YAML)
3. Check logs for "Error finalizing review"
4. Ensure trail files have correct structure

### Wrong trails selected

Trail selection priority:
1. Most overdue (by `next_review` date)
2. Active trails without review scheduled
3. Random from active trails

Paused/completed/abandoned trails are excluded from random selection but can still be reviewed manually.

## Future Enhancements

- [ ] Per-user poll time preferences (database)
- [ ] Weekly/monthly trail digests
- [ ] Progress charts from trail history
- [ ] Integration with `/focus` and drift detection
- [ ] Multi-trail batch reviews
- [ ] Trail velocity trends over time
