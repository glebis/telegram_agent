# ✅ SRS System - Setup Complete!

The Spaced Repetition System for your Obsidian vault is now fully operational.

## 📊 Current Status

### Database
- **Location**: `~/ai_projects/telegram_agent/data/srs/schedule.db`
- **Cards seeded**: 52 evergreen ideas
- **Cards due now**: 3 (manually set for testing)

### Background Services (launchd)
✅ **Vault Sync** - Runs every hour
✅ **Morning Batch** - Runs daily at 9am

Check status:
```bash
~/ai_projects/telegram_agent/scripts/srs_service.sh status
```

### Bot Integration
✅ Handlers registered in `src/bot/bot.py`
✅ Commands available: `/review`, `/srs_stats`
✅ Develop button integrated with Claude Code

## 🎯 Test It Now

### 1. Test /review Command in Telegram

Send this message to your bot:
```
/review
```

You should see 3 cards with:
- Card content (first 1000 chars)
- Related notes
- Rating buttons: Again | Hard | Good | Easy
- **Develop** button

### 2. Test Rating

Click any rating button (Good, Easy, etc.) and the card will:
- Update its schedule
- Update vault frontmatter
- Show next review date

### 3. Test Develop Button

Click **🔧 Develop** and it will:
- Start a new Claude Code session
- Set working directory to vault
- Provide full note context + backlinks
- Let you edit/expand the note in conversation

### 4. Check Stats

```
/srs_stats
```

Shows:
- Total cards by type
- Cards due now
- Average ease factor
- Average interval

## 🔧 Management Commands

```bash
# Service management
~/ai_projects/telegram_agent/scripts/srs_service.sh start
~/ai_projects/telegram_agent/scripts/srs_service.sh status
~/ai_projects/telegram_agent/scripts/srs_service.sh logs

# Manual operations
~/ai_projects/telegram_agent/scripts/srs_service.sh test-sync
~/ai_projects/telegram_agent/scripts/srs_service.sh test-batch

# Database queries
sqlite3 ~/ai_projects/telegram_agent/data/srs/schedule.db "
  SELECT COUNT(*) as total_cards FROM srs_cards WHERE srs_enabled = 1;
"
```

## 📅 What Happens Next

### Hourly (on the hour)
- Vault is synced to database
- New notes with `srs_enabled: true` are added
- Frontmatter changes are reflected in DB

### Daily at 9am
- Morning batch checks for due cards
- Sends 5 cards (configurable) to Telegram
- Only sends once per day

### When You Review
1. Card appears in Telegram
2. You rate it (Again/Hard/Good/Easy)
3. SM-2 algorithm calculates next interval
4. Vault frontmatter is updated
5. Card resurfaces at scheduled time

## 📝 Adding New Notes to SRS

### Automatic (Evergreen Ideas)
Any note in `Ideas/∞→*.md` with frontmatter gets auto-enabled

### Manual (Any Note)
Add to frontmatter:
```yaml
---
srs_enabled: true
srs_next_review: 2026-01-25
srs_interval: 1
srs_ease_factor: 2.5
srs_repetitions: 0
---
```

Then sync:
```bash
~/ai_projects/telegram_agent/scripts/srs_service.sh test-sync
```

## 🎨 Customization

### Change Morning Batch Time
Edit: `~/Library/LaunchAgents/com.glebkalinin.srs.morning.plist`

Change hour (24-hour format):
```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>8</integer>  <!-- Change to 8am -->
    <key>Minute</key>
    <integer>30</integer> <!-- Change to 8:30am -->
</dict>
```

Then reload:
```bash
~/ai_projects/telegram_agent/scripts/srs_service.sh restart
```

### Change Batch Size
```bash
cd ~/ai_projects/telegram_agent/src/services/srs
python3 srs_scheduler.py --config morning_batch_size "7"
```

## 🐛 Troubleshooting

### Cards not appearing in /review
```bash
# Check due cards
cd ~/ai_projects/telegram_agent/src/services/srs
python3 srs_algorithm.py --due

# Re-sync vault
~/ai_projects/telegram_agent/scripts/srs_service.sh test-sync
```

### Morning batch not sending
```bash
# Check logs
~/ai_projects/telegram_agent/scripts/srs_service.sh logs

# Test manually
~/ai_projects/telegram_agent/scripts/srs_service.sh test-batch
```

### Bot not responding to /review
- Restart bot: `pm2 restart telegram-agent`
- Check bot logs: `pm2 logs telegram-agent`
- Verify handlers registered in `src/bot/bot.py`

## 📚 Documentation

- **Quick Start**: `SRS_QUICKSTART.md`
- **Integration Guide**: `docs/SRS_INTEGRATION.md`
- **Detailed Docs**: `src/services/srs/README.md`

## 🎉 You're All Set!

The system is running! Cards will start appearing based on their schedule. Test it now with `/review` in Telegram.

### First Steps
1. Open Telegram and send `/review` to your bot
2. Rate the 3 test cards
3. Watch them reschedule automatically
4. Check stats with `/srs_stats`
5. Try the **Develop** button on a card

Enjoy your spaced repetition system! 🚀
