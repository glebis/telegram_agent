## /debug-bot - Debug Telegram Bot

Systematically diagnose why the Telegram bot is unresponsive or misbehaving. Always diagnose BEFORE fixing.

### Usage
- `/debug-bot` — full diagnostic check
- `/debug-bot logs` — show recent errors from logs
- `/debug-bot webhook` — check webhook status only

### Steps

1. **Check process status**:
   ```bash
   ps aux | grep "uvicorn.*src.main" | grep -v grep
   launchctl list | grep telegram-agent.bot
   lsof -i :8847
   ```
   If no process is running, skip to step 5.

2. **Check health endpoint**:
   ```bash
   curl -s http://localhost:8847/health | python3 -m json.tool
   ```
   Look at `status`, `bot_initialized`, and `uptime_seconds`.

3. **Check recent log errors** (last 200 lines):
   ```bash
   grep '"level":"ERROR"' /Users/server/ai_projects/telegram_agent/logs/app.log | tail -20
   ```
   Also check launchd stderr:
   ```bash
   tail -30 /Users/server/ai_projects/telegram_agent/logs/launchd_bot.err
   ```

4. **Check webhook status**:
   ```bash
   TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" /Users/server/ai_projects/telegram_agent/.env | cut -d= -f2- | tr -d '"' | tr -d "'")
   curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo" | python3 -m json.tool
   ```
   Verify: `url` is set to `https://tgbot.realitytouch.org/webhook`, `pending_update_count` < 10, no recent `last_error_message`.

5. **If bot needs restart**, use `clean_restart.sh` (NEVER manual launchctl):
   ```bash
   bash /Users/server/ai_projects/telegram_agent/scripts/clean_restart.sh
   ```

6. **Report findings** to user with: process status, health result, webhook info, recent errors, and recommended action.

### Known Failure Modes

Check these IN ORDER — most common first:

| Symptom | Likely Cause | Check |
|---------|-------------|-------|
| Bot not responding at all | Process crashed or tunnel dead | `ps aux`, `lsof -i :8847` |
| Messages hang for 30s+ | asyncio deadlock in DB lookup | Logs for "wait_for" or "timeout" |
| "database is locked" in logs | WAL mode / busy_timeout issue | `sqlite3 ... "PRAGMA journal_mode;"` |
| Webhook 401 errors | Secret token mismatch | Compare `TELEGRAM_WEBHOOK_SECRET` in .env vs webhook config |
| Webhook URL empty | Tunnel died, webhook not re-registered | Check cloudflared process, re-run restart |
| Health check restart loops | Health script kills bot before it fully starts | Check `logs/launchd_bot.err` for startup errors |

### Message Processing Path (for tracing hangs)

```
webhook_endpoint (src/main.py:883)
  → dedup check → semaphore acquire
  → create_tracked_task(process_in_background)
    → MessageBuffer.add_message (src/services/message_buffer.py)
      → 2.5s buffer window → CombinedMessage
    → process_combined_message (src/bot/combined_processor.py)
      → plugin routing → command routing → content routing
      → reply context DB lookup (10s timeout via asyncio.wait)
    → send_message_sync (src/bot/handlers/formatting.py)
      → subprocess isolation (NEVER direct async)
```

### Key Files
- `src/main.py` — webhook entry, dedup, concurrency
- `src/bot/combined_processor.py` — message routing, reply context
- `src/services/message_buffer.py` — message buffering/combining
- `src/bot/handlers/formatting.py` — subprocess-isolated reply sending
- `logs/app.log` — structured JSON logs
- `logs/launchd_bot.err` — uvicorn stderr

### Notes
- Bot takes ~15-20 seconds to fully initialize after restart
- `last_error_date` in webhook info is STALE — persists long after errors resolve; check recency
- Signal `-9` in launchctl list = process was killed (OOM), not a clean exit
- Token is in `.env` (NOT `.env.local`)
- All external I/O in handlers MUST use subprocess isolation — direct async calls will deadlock
