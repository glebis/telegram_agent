# Trail Review - Quick Start Guide

Get trail review polls running in 5 minutes.

## Setup

### 1. Add Environment Variables

Edit `.env.local`:

```bash
# Enable trail reviews
TRAIL_REVIEW_ENABLED=true

# Your chat ID (required)
TRAIL_REVIEW_CHAT_ID=123456789

# Optional: customize poll times (default: 09:00,14:00,20:00)
TRAIL_REVIEW_TIMES=09:00,14:00,20:00
```

### 2. Get Your Chat ID

**Option A: Check logs**
1. Send any message to your bot
2. Check logs for: `chat_id=123456789`

**Option B: Use @userinfobot**
1. Start chat with https://t.me/userinfobot
2. It will reply with your ID

### 3. Restart the Bot

```bash
# If using systemd
sudo systemctl restart telegram-agent

# If using launchd (macOS)
launchctl stop com.telegram-agent.bot
launchctl start com.telegram-agent.bot

# If running manually
# Ctrl+C and restart
```

## Verify Setup

Check logs for:
```
📅 Scheduled trail review at 9:00
📅 Scheduled trail review at 14:00
📅 Scheduled trail review at 20:00
✅ Trail review scheduler configured with 3 daily polls
```

## Manual Testing

Before waiting for scheduled polls, test manually:

```
# Show trails due for review
/trail:list

# Review most urgent trail
/trail

# Review specific trail
/trail:review Agentic Knowledge Work
```

## Expected Behavior

### Scheduled Polls

At each configured time (e.g., 09:00), the bot will:
1. Select a trail due for review (prioritizes overdue)
2. Send intro message with current trail status
3. Start poll sequence (4 questions)

### Poll Sequence

**Poll 1: Velocity**
```
🚀 Trail velocity for 'Project Name'?
○ 🔥 High (moving fast)
○ ⚡ Medium (steady progress)
○ 🐢 Low (slow/background)
○ ⏸️ Paused
```

**Poll 2: Status**
```
📊 Status for 'Project Name'?
○ ✅ Active (working on it)
○ ⏸️ Paused (on hold)
○ 🎯 Completed
○ ❌ Abandoned
```

**Poll 3: Stage** (varies by trail direction)
```
🔬 Research stage for 'Project Name'?
○ 🔍 Exploring
○ 📚 Synthesizing
○ 🔗 Integrating
○ 💡 Applying
```

**Poll 4: Next Review**
```
📅 When to review 'Project Name' again?
○ 🔔 Tomorrow (urgent)
○ 📆 In 1 week
○ 📆 In 2 weeks
○ 📆 In 1 month
```

### Completion

After answering all polls:
```
✅ Trail Review Complete: Project Name

Updates:
• velocity → high
• status → active
• next_review → 2026-02-03
• last_updated → 2026-01-27
```

## Trail File Requirements

Trails must:
1. Be in `~/Research/vault/Trails/`
2. Follow naming: `Trail - Name.md`
3. Have frontmatter:

```yaml
---
type: trail
status: active
velocity: medium
next_review: 2026-01-27
direction: research  # or building, learning
---
```

## Troubleshooting

### No polls received

**Check 1: Environment variables**
```bash
grep TRAIL_REVIEW .env.local
```

Should show:
```
TRAIL_REVIEW_ENABLED=true
TRAIL_REVIEW_CHAT_ID=123456789
```

**Check 2: Bot logs**
```bash
tail -f logs/app.log | grep -i trail
```

Look for:
- `Trail review scheduler configured`
- `Scheduled trail review at...`

**Check 3: Trails exist**
```bash
ls ~/Research/vault/Trails/Trail*.md
```

Should list trail files.

**Check 4: Trail status**
Polls only go to `active` or `paused` trails. Check frontmatter:
```bash
head -15 ~/Research/vault/Trails/Trail\ -\ *.md
```

### Wrong poll times

**Time zone**: Times are in bot server's local time zone.

Check current time:
```bash
date "+%H:%M"
```

**Format**: Must be 24-hour format with colon:
```bash
# Correct
TRAIL_REVIEW_TIMES=09:00,14:00,20:00

# Wrong
TRAIL_REVIEW_TIMES=9am,2pm,8pm
```

### Polls don't update files

**Check 1: File permissions**
```bash
ls -l ~/Research/vault/Trails/
```

Bot user must have write access.

**Check 2: Frontmatter format**
Ensure YAML is valid:
```yaml
---
type: trail
status: active
---
```

Not:
```
---
type = trail  # Wrong: not YAML
status: "active"  # OK but quotes not needed
---
```

**Check 3: Logs**
```bash
tail -f logs/app.log | grep "Error finalizing review"
```

## Customization

### Different Poll Times

Weekend vs weekday schedules:
```bash
# Weekdays (in your deployment script)
TRAIL_REVIEW_TIMES=07:00,12:00,18:00

# Weekends (restart with different config)
TRAIL_REVIEW_TIMES=10:00,16:00,21:00
```

### Disable Temporarily

```bash
TRAIL_REVIEW_ENABLED=false
```

Restart bot. Re-enable by setting to `true`.

### Multiple Chat IDs

Currently supports one chat ID. For multiple users:
1. Each user runs their own bot instance, or
2. Extend `trail_scheduler.py` to support multiple chat IDs from database

## Next Steps

1. **Set up trails**: Create trail files in vault if not already existing
2. **Configure times**: Adjust `TRAIL_REVIEW_TIMES` to your schedule
3. **Test manually**: Use `/trail` before first scheduled poll
4. **Monitor**: Check logs after first scheduled poll time
5. **Iterate**: Adjust poll times based on usage patterns

See [TRAIL_REVIEW.md](TRAIL_REVIEW.md) for full documentation.
