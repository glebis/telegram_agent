# Launchd setup (macOS)

These plist files keep the Telegram agent running after crashes and reboots, and add a periodic health check that can restart the bot if the HTTP/Telegram checks fail.

## Files
- `ops/launchd/com.telegram-agent.bot.plist` — runs `scripts/run_agent_launchd.sh` with `KeepAlive`/`RunAtLoad`.
- `ops/launchd/com.telegram-agent.health.plist` — runs `scripts/health_check.sh` every 60s; restarts the bot via `launchctl kickstart` if a check fails.

Paths inside the plists point to `/Users/server/ai_projects/telegram_agent`; edit them if you move the repo.

## Install / reload
```bash
# 1) Copy plists into LaunchAgents (user scope)
mkdir -p ~/Library/LaunchAgents
cp ops/launchd/com.telegram-agent.bot.plist ~/Library/LaunchAgents/
cp ops/launchd/com.telegram-agent.health.plist ~/Library/LaunchAgents/

# 2) Reload (idempotent)
launchctl bootout gui/$(id -u)/com.telegram-agent.bot 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.telegram-agent.health 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.telegram-agent.bot.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.telegram-agent.health.plist
launchctl kickstart -k gui/$(id -u)/com.telegram-agent.bot
```

## Verify
```bash
launchctl print gui/$(id -u)/com.telegram-agent.bot | head
launchctl print gui/$(id -u)/com.telegram-agent.health | head
tail -f logs/launchd_bot.log logs/launchd_bot.err
tail -f logs/launchd_health.log logs/launchd_health.err
curl -fsS http://127.0.0.1:8001/health
```

## Config knobs
- `PORT`, `HOST`, `ENV_FILE`, `SERVICE_LABEL` can be overridden inside the plist or at load time with `launchctl setenv`.
- `.env.local` is sourced by both scripts; set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL` there to enable Telegram webhook validation.
- `VENV_PATH` (optional) can point to a Python venv; `PYTHON_BIN` (optional) defaults to `python3`.

## Uninstall
```bash
launchctl bootout gui/$(id -u)/com.telegram-agent.bot 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.telegram-agent.health 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.telegram-agent.bot.plist
rm -f ~/Library/LaunchAgents/com.telegram-agent.health.plist
```
