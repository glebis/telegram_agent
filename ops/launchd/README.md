# Launchd setup (macOS)

Plist templates in this directory keep all Telegram agent services running after crashes and reboots. Paths use `__PROJECT_ROOT__`, `__PYTHON_BIN__`, and `__HOME__` placeholders that are substituted at install time.

## Services

| Plist | Description |
|---|---|
| `com.telegram-agent.bot` | Main bot (port 8847, KeepAlive) |
| `com.telegram-agent.bot-staging` | Staging bot (port 8848, manual start) |
| `com.telegram-agent.health` | Health check every 60s |
| `com.telegram_agent.worker` | Worker queue (KeepAlive) |
| `com.telegram-agent.daily-health-review` | Daily at 09:30 |
| `com.telegram-agent.daily-research` | Daily at 10:00 |
| `com.telegram-agent.task-monitor` | Every hour |
| `com.telegram-agent.architecture-review-am` | Daily at 09:00 |
| `com.telegram-agent.architecture-review-pm` | Daily at 21:00 |
| `com.telegram-agent.ai-coding-tools-research` | Daily at 10:00 |

## Install / reload

```bash
# Install all services (auto-detects paths)
scripts/install_launchd.sh

# Install specific services (substring match)
scripts/install_launchd.sh bot health

# Preview what would be installed
scripts/install_launchd.sh --dry-run

# Override Python binary
PYTHON_BIN=/usr/local/bin/python3.12 scripts/install_launchd.sh
```

## Verify

```bash
launchctl print gui/$(id -u)/com.telegram-agent.bot | head
tail -f logs/launchd_bot.log logs/launchd_bot.err

# Ensure no leftover placeholders
grep -r '__PROJECT_ROOT__\|__PYTHON_BIN__\|__HOME__' ~/Library/LaunchAgents/com.telegram*
```

## Uninstall

```bash
# Remove all telegram-agent services
scripts/uninstall_launchd.sh

# Preview
scripts/uninstall_launchd.sh --dry-run
```

## Config knobs

- `PORT`, `HOST`, `ENV_FILE`, `SERVICE_LABEL` can be overridden inside the plist or at load time with `launchctl setenv`.
- `.env.local` is sourced by both scripts; set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL` there to enable Telegram webhook validation.
- `PYTHON_BIN` env var overrides auto-detection at install time.
