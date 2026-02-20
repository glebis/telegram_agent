## /restart - Restart Production Bot

Restart the production Telegram bot service using the clean restart script.

### Usage
- `/restart` — restart production
- `/restart staging` — restart staging

### Steps

1. **Run the clean restart script**:
   ```bash
   bash /Users/server/ai_projects/telegram_agent/scripts/clean_restart.sh
   ```
   For staging, add `--staging` flag.

2. **Verify webhook** (production only):
   ```bash
   TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" /Users/server/ai_projects/telegram_agent/.env | cut -d= -f2- | tr -d '"' | tr -d "'")
   curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo" | python3 -m json.tool
   ```
   Confirm `url` is set and `pending_update_count` is reasonable.

3. **Report**: Show the user the health status, launchd status, tunnel PID, and webhook info.

### Notes
- The restart script handles: unload plist, kill orphan processes, kill stale tunnels, reload plist, health check with retry loop
- Bot takes ~15-20 seconds to fully initialize
- Token is in `.env` (NOT `.env.local`) — use `.env` when checking webhook manually
- The plist `ENV_FILE` is set to `.env.local`, but the app loads tokens from `.env` as well
- If the script reports FAILED, check `logs/app.log` and `logs/launchd_bot.err` for details
