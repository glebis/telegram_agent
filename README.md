# Telegram Agent

A personal Telegram bot with Claude Code SDK integration, deep research, voice synthesis, accountability tracking, spaced repetition, and Obsidian vault integration.

## Features

**AI & Code** — Claude Code sessions with streaming, session persistence, locked mode, multi-part prompts, reply threading, tool display, auto-file sending; OpenCode for 75+ LLM providers via LiteLLM; `/meta` for self-modification

**Research & Knowledge** — Deep web research pipeline with Obsidian reports; spaced repetition (SM-2); trail reviews; Obsidian wikilinks and note viewing; batch collect mode

**Voice & Media** — Groq Whisper transcription with LLM correction; multi-provider TTS (Groq/OpenAI); image analysis with vector similarity; gallery browsing; PDF processing

**Accountability** — Habit/medication/value/commitment trackers; streak dashboard; contextual polls with sentiment analysis; scheduled check-ins

**Privacy & Data** — Per-user data retention policies; data export; data deletion; health data consent

**Platform** — Webhook with HMAC-SHA256 validation; Docker, systemd, launchd deployment; proactive task scheduler; CI/CD pipeline; plugin system

## Quick Start

```bash
git clone https://github.com/glebis/telegram_agent.git
cd telegram_agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_wizard.py        # interactive — walks through all config
python scripts/start_dev.py start --port 8000
```

The wizard covers: bot token, webhook secret, API keys, optional features (Obsidian, Claude Code), database init, and verification. It's idempotent — run again to update config.

## Bot Commands

### Core
| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Show all commands |
| `/menu` | Command menu by category |
| `/settings` | Settings hub (voice, keyboard, trackers) |
| `/language` | Change bot language |
| `/note <name>` | View Obsidian vault note |
| `/gallery` | Browse uploaded images |

### Claude Code
| Command | Description |
|---------|-------------|
| `/claude <prompt>` | Execute prompt |
| `/claude:new` | New session |
| `/claude:sessions` | List sessions |
| `/claude:lock` / `unlock` | Toggle locked mode (all messages → Claude) |
| `/claude:reset` | Reset session |
| `/claude:help` | Claude help |
| `/session` | Active session info |
| `/session rename <name>` | Rename session |
| `/meta <prompt>` | Work on the bot itself |

### OpenCode
| Command | Description |
|---------|-------------|
| `/opencode <prompt>` | Run prompt (75+ LLM providers) |
| `/opencode:new` | New session |
| `/opencode:sessions` | List sessions |
| `/opencode:reset` | Clear session |
| `/opencode:help` | OpenCode help |

### Research & Collect
| Command | Description |
|---------|-------------|
| `/research <topic>` | Deep web research → vault |
| `/research:help` | Research options |
| `/collect:start` | Begin collecting items |
| `/collect:go` | Process collected items |
| `/collect:status` | Show queue |
| `/collect:stop` | Cancel collection |

### Learning & Review
| Command | Description |
|---------|-------------|
| `/review` | SRS cards due for review |
| `/srs_stats` | Spaced repetition stats |
| `/trail` | Next trail for review |
| `/trail:list` | All trails due |

### Accountability
| Command | Description |
|---------|-------------|
| `/track` | Today's tracker overview |
| `/track:add [type] <name>` | Create tracker |
| `/track:done <name>` | Check in as done |
| `/track:skip <name>` | Skip for today |
| `/track:list` | All trackers |
| `/track:remove <name>` | Archive tracker |
| `/streak` | Streak dashboard |

### Polls & Tracking
| Command | Description |
|---------|-------------|
| `/polls` | Poll statistics |
| `/polls:send` | Trigger next poll |
| `/polls:pause` / `resume` | Toggle auto-polls |

### Privacy
| Command | Description |
|---------|-------------|
| `/privacy` | Privacy info & consent |
| `/mydata` | Export your data |
| `/deletedata` | Delete your data |

### Memory
| Command | Description |
|---------|-------------|
| `/memory` | View chat memory |
| `/memory edit <text>` | Replace memory |
| `/memory add <text>` | Append to memory |
| `/memory export` | Download CLAUDE.md |
| `/memory reset` | Reset to default |

### Tasks
| Command | Description |
|---------|-------------|
| `/tasks` | List scheduled tasks |
| `/tasks pause <id>` | Pause a task |
| `/tasks resume <id>` | Resume a task |
| `/tasks history <id>` | Last 5 runs |

### System
| Command | Description |
|---------|-------------|
| `/heartbeat` | System health check (admin) |

## Configuration

Copy `.env.example` to `.env.local` and configure. Key groups:

- **Core** — `TELEGRAM_BOT_TOKEN` (required), `TELEGRAM_WEBHOOK_SECRET`, `ENVIRONMENT`, `PORT`
- **LLM keys** — `OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `LLM_MODEL`
- **Claude Code** — `CLAUDE_CODE_WORK_DIR`, `CLAUDE_CODE_MODEL`, `CLAUDE_ALLOWED_TOOLS`
- **Webhook safety** — `WEBHOOK_MAX_BODY_BYTES`, `WEBHOOK_RATE_LIMIT`, `WEBHOOK_USE_HTTPS`
- **Schedulers** — `POLLING_ENABLED`, `TRAIL_REVIEW_ENABLED`, `HEARTBEAT_CHAT_IDS`
- **Tunneling** — `TUNNEL_PROVIDER` (ngrok / cloudflare / tailscale / none), `WEBHOOK_BASE_URL`

See [`.env.example`](.env.example) for the full documented list with defaults.

## Issue Tracking

This project uses [Beads](https://github.com/synthase/beads) for local issue tracking. Issues are synced from GitHub and stored in `.beads/beads.db`. Use `/bd` in the Telegram bot or `beads` CLI to manage issues.

## Development

### Project Structure

```
telegram_agent/
├── src/
│   ├── bot/
│   │   ├── handlers/              # Command handlers
│   │   │   ├── core_commands.py       # /start, /help, /menu, /settings
│   │   │   ├── claude_commands.py     # /claude:*, /meta, /session
│   │   │   ├── opencode_commands.py   # /opencode:*
│   │   │   ├── research_commands.py   # /research
│   │   │   ├── collect_commands.py    # /collect:*
│   │   │   ├── accountability_commands.py  # /track, /streak
│   │   │   ├── memory_commands.py     # /memory
│   │   │   ├── task_commands.py       # /tasks
│   │   │   ├── trail_handlers.py      # /trail
│   │   │   ├── srs_handlers.py        # /review, /srs_stats
│   │   │   ├── poll_handlers.py       # /polls
│   │   │   ├── privacy_commands.py    # /privacy, /mydata, /deletedata
│   │   │   ├── language_commands.py   # /language
│   │   │   ├── heartbeat_commands.py  # /heartbeat
│   │   │   ├── note_commands.py       # /note
│   │   │   ├── mode_commands.py       # /mode, /analyze, /coach
│   │   │   └── voice_settings_commands.py  # Settings callbacks
│   │   ├── message_handlers.py    # Text, image, voice, video routing
│   │   ├── callback_handlers.py   # Inline button callbacks
│   │   ├── combined_processor.py  # Message buffering & routing
│   │   └── bot.py                 # Bot initialization
│   ├── services/          # Business logic & external integrations
│   ├── models/            # SQLAlchemy ORM models
│   ├── core/              # Config, database, image processing
│   ├── tunnel/            # Pluggable tunnel providers (ngrok, cloudflare, tailscale)
│   ├── api/               # FastAPI admin endpoints
│   ├── middleware/         # Request middleware
│   ├── plugins/           # Plugin system
│   └── utils/             # Helpers (task tracker, subprocess, etc.)
├── config/                # YAML configs (modes, settings, defaults)
├── plugins/               # Plugin directory (claude_code, codex, pdf)
├── scripts/               # Setup wizard, dev server, health checks
├── locales/               # i18n (en, ru)
├── tests/                 # Test suite
├── deploy/                # Deployment configs (Docker, systemd, launchd)
└── docs/                  # Documentation
```

### Test & Lint

```bash
# Lint + format
python -m black src/ tests/ && python -m isort src/ tests/ && python -m flake8 src/ tests/

# Type check
python -m mypy src/

# Run tests
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=html
```

## Deployment

**Docker** (recommended) — `docker-compose up -d` with volumes for `data/` and `logs/`.

**systemd** — `sudo cp deploy/telegram-agent.service /etc/systemd/system/` and configure paths. Or use the automated installer: `sudo bash deploy/install.sh`.

**launchd** (macOS) — Plist files in `~/Library/LaunchAgents/com.telegram-agent.*.plist` for bot, health monitor, daily tasks.

**Railway** — Set `RAILWAY_PUBLIC_DOMAIN` and deploy. Tunnel auto-detected.

## Documentation

| Document | Description |
|----------|-------------|
| [FEATURES.md](docs/FEATURES.md) | Complete feature reference |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | Development guide |
| [PLUGINS.md](docs/PLUGINS.md) | Plugin development |
| [SRS_INTEGRATION.md](docs/SRS_INTEGRATION.md) | Spaced repetition details |
| [TRAIL_REVIEW.md](docs/TRAIL_REVIEW.md) | Trail review system |
| [QUICKREF.md](docs/QUICKREF.md) | Quick reference |
| [CHANGELOG.md](CHANGELOG.md) | Recent changes |

## License

[MIT License](LICENSE)
