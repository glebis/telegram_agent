# Telegram Agent v0.8

A Telegram bot with Claude Code SDK integration, voice synthesis, deep research, accountability tracking, image processing, and Obsidian vault integration. Features data retention enforcement, interactive setup wizard, CI/CD pipeline, and cross-platform deployment.

## Features

### Core Features
- **Claude Code Integration**: Interactive AI sessions with streaming, session persistence, auto-naming
- **Deep Research Mode**: Multi-stage research pipeline with web search, synthesis, and Obsidian reports (`/research`)
- **Voice & Audio**: Groq Whisper transcription, LLM correction, Orpheus TTS voice synthesis (6 voices, 3 emotions)
- **Accountability & Wellness**: Habit/medication/value trackers, scheduled check-ins, contextual polls with sentiment analysis
- **Spaced Repetition System**: Review vault ideas with SM-2 algorithm scheduling ([details](docs/FEATURES.md#spaced-repetition-system-srs))
- **Image Processing Pipeline**: Download, compress, analyze with AI, vector similarity search
- **Design Skills Integration**: Automatic UI/UX best practices from Impeccable Style, UI Skills, Rams.ai ([details](docs/FEATURES.md#design-skills-integration))
- **Data Retention**: Per-user GDPR-compliant data lifecycle (1 month / 6 months / 1 year / forever)
- **Proactive Task Framework**: Scheduled background tasks via launchd
- **Web Admin Interface**: User management, chat monitoring, and bot statistics
- **MCP Integration**: Auto-discovery and execution of MCP tools
- **Security Hardened**: HMAC-SHA256 webhook validation, timing-safe comparison, image/payload size limits
- **CI/CD Pipeline**: Automated linting, type checking, tests, and security scanning on every push

### Claude Code SDK Integration
- **Interactive AI Sessions**: Full Claude Code SDK integration with streaming responses
- **Session Persistence**: Sessions are stored and can be resumed across conversations
- **Claude Locked Mode**: Toggle continuous conversation mode without `/claude` prefix
- **Reply Context**: Reply to any Claude message to continue in that specific session
- **Text Messages to Claude**: In locked mode, all text messages (without `/claude` prefix) route to Claude Code
- **Session Controls**: Inline keyboard buttons for Reset, Continue, and Lock/Unlock
- **Tool Display**: Real-time display of Claude's actions (Read, Write, Bash, Skills, Tasks, Web searches)
- **Auto-send Files**: Generated files (PDF, images, audio, video) are automatically sent to users
- **Long Message Handling**: Automatic splitting of responses exceeding Telegram limits

> 📖 **For detailed feature documentation, see [docs/FEATURES.md](docs/FEATURES.md)**

### Message Buffering System
- **Multi-part Prompts**: Send `/claude` followed by multiple messages - all are combined into one prompt
- **Smart Combining**: Buffer waits 2.5 seconds after last message before executing
- **Media Support**: Combine text, images, voice messages, and documents in a single request
- **Voice & Video Transcription**: Automatically transcribe voice/video messages and optionally route to Claude

### Deep Research
- **`/research <topic>`**: 4-stage pipeline (plan → search → synthesize → report)
- **Auto-PDF generation**: Reports saved to Obsidian vault with citations
- **Vault linking**: Automatically cross-references related notes

### Obsidian Integration
- **Wikilinks Support**: Clickable `[[wikilinks]]` with deep link navigation
- **Note Viewing**: View Obsidian notes directly in Telegram via `/note` command and deep links
- **Vault Operations**: Read, search, and edit notes through Claude sessions

### Batch Processing
- **Collect Mode**: Accumulate multiple messages, images, voice memos, or videos before processing
- **Batch Claude Processing**: Send collected items together to Claude for comprehensive analysis
- **Queue Management**: View, clear, or cancel collection without processing

### Accountability & Wellness
- **Trackers**: Habit, medication, value, and commitment tracking with configurable frequency
- **Check-ins**: Scheduled prompts with status tracking (completed, skipped, partial)
- **Polls**: Contextual polls with sentiment analysis and insight generation
- **Voice Synthesis**: Text-to-speech responses via Groq Orpheus TTS (6 voices, 3 emotion styles)

### Privacy & Data Retention
- **Per-user retention policies**: 1 month, 6 months, 1 year, or forever
- **Automatic enforcement**: Periodic deletion of messages, poll responses, and check-ins older than the user's configured retention
- **Health data consent**: GDPR Article 9 compliant consent tracking

### Scheduled Automations
- **Daily Health Review**: Automated health data summary sent at 9:30am via launchd
- **Daily Research Digest**: AI-curated research summary at 10:00am
- **launchd Service**: System service configuration for reliable background operation

### Admin Features
- **Admin Contacts**: Manage authorized users for Claude Code access
- **Messaging API**: Send messages programmatically to admin contacts

## Quick Start

### Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key (or other LLM provider)
- Tunnel provider (one of): ngrok (dev default), cloudflared (prod default), or Tailscale Funnel
- Claude Code SDK (for AI session integration): `pip install claude-code-sdk`
- Anthropic subscription (Claude Code uses subscription, not API credits)

### Interactive Setup (Recommended)

The setup wizard walks through all configuration interactively:

```bash
git clone https://github.com/glebis/telegram_agent.git
cd telegram_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_wizard.py
```

The wizard covers: preflight checks, bot token, webhook secret, API keys, optional features (Obsidian vault, Claude Code), database initialization, and verification. It's idempotent - run again to update configuration.

After the wizard completes:
```bash
python scripts/start_dev.py start --port 8000
```

See [docs/dev-setup-shell.md](docs/dev-setup-shell.md) for manual setup or finer control.

### Manual Installation

1. Clone and setup:
```bash
git clone https://github.com/glebis/telegram_agent.git
cd telegram_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env.local
# Edit .env.local with your API keys and settings
```

3. Initialize database:
```bash
python -m src.core.database init
```

4. Start the application:
```bash
python scripts/start_dev.py start --port 8000
```
This auto-starts FastAPI, the configured tunnel provider (ngrok by default), and webhook setup.

## Configuration

### Environment Variables

See `.env.example` for the complete, documented list (defaults included). Highlights:

- **Core:** `TELEGRAM_BOT_TOKEN` (required), `TELEGRAM_WEBHOOK_SECRET`, `ENVIRONMENT`, `PORT`, `HOST`, `LOG_LEVEL`.
- **LLM keys:** `OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `LLM_MODEL` (`gpt-4o-mini`), `EMBEDDING_MODEL` (`clip-ViT-B-32`).
- **Claude Code:** `CLAUDE_CODE_WORK_DIR` (default `~/Research/vault`), `CLAUDE_CODE_MODEL`, `CLAUDE_QUERY_TIMEOUT`, `SESSION_IDLE_TIMEOUT_MINUTES`, `CLAUDE_ALLOWED_TOOLS` / `CLAUDE_DISALLOWED_TOOLS`.
- **Webhook safety:** `WEBHOOK_MAX_BODY_BYTES`, `WEBHOOK_RATE_LIMIT`, `WEBHOOK_RATE_WINDOW_SECONDS`, `WEBHOOK_MAX_CONCURRENCY`, `WEBHOOK_USE_HTTPS` (default `true`), `API_MAX_BODY_BYTES`.
- **Media limits:** `MAX_IMAGE_BYTES` (default 6 MB), `ALLOWED_IMAGE_EXTS`.
- **Schedulers:** `POLLING_ENABLED`, `POLLING_CHAT_IDS`, `POLLING_INTERVAL_MINUTES`, `TRAIL_REVIEW_ENABLED`, `TRAIL_REVIEW_CHAT_ID`, `TRAIL_REVIEW_TIMES`.
- **Proactive tasks:** `GOOGLE_API_KEY`, `GOOGLE_SEARCH_CX`, `FIRECRAWL_API_KEY` (fail-fast checks added to the task runner).
- **Tunneling:** `TUNNEL_PROVIDER` (`ngrok` / `cloudflare` / `tailscale` / `none`; auto-detected from environment), `TUNNEL_PORT`, `NGROK_PORT`, `WEBHOOK_BASE_URL`, `CF_TUNNEL_NAME`, `CF_CREDENTIALS_FILE`, `CF_CONFIG_FILE`, `TAILSCALE_HOSTNAME`, `RAILWAY_PUBLIC_DOMAIN` / `RAILWAY_SERVICE_URL` / `RAILWAY_STATIC_URL` / `RAILWAY_APP_URL`.

Optional tooling (warned by preflight, non-blocking):
- `marker_single` (marker-pdf), `ffmpeg`, `ngrok` / `cloudflared` / `tailscale` (tunnel provider), `claude` CLI.

### Mode Configuration

Edit `config/modes.yaml` to customize analysis modes and presets:

```yaml
modes:
  default:
    prompt: "Describe the image in ≤40 words..."
    embed: false
  artistic:
    embed: true
    presets:
      - name: "Critic"
        prompt: "Analyze composition, color theory..."
```

## Usage

### Feature Deep Dives

For detailed usage examples and workflows, see [docs/FEATURES.md](docs/FEATURES.md):
- [Spaced Repetition System](docs/FEATURES.md#spaced-repetition-system-srs) - Setup, rating, scheduling
- [Claude Code Integration](docs/FEATURES.md#claude-code-integration) - Sessions, locked mode, tool display
- [Design Skills Integration](docs/FEATURES.md#design-skills-integration) - UI/UX guidance
- [Session Management](docs/FEATURES.md#session-management) - Auto-naming, controls
- [Reply Context System](docs/FEATURES.md#reply-context-system) - Threading and context
- [Collect Mode](docs/FEATURES.md#collect-mode-batch-processing) - Batch processing workflows
- [Plugin System](docs/FEATURES.md#plugin-system) - Architecture and development
- [Voice & Video Transcription](docs/FEATURES.md#voice--video-transcription) - Groq Whisper, correction
- [Obsidian Integration](docs/FEATURES.md#obsidian-integration) - Wikilinks, vault operations

### Bot Commands

#### General
- `/start` - Initialize chat and show welcome message
- `/help` - Show available commands

#### Image Analysis
- `/mode default` - Switch to default analysis mode
- `/mode artistic Critic` - Switch to artistic mode with Critic preset
- `/analyze` - Alias for artistic Critic mode
- `/coach` - Alias for artistic Photo-coach mode

#### Claude Code (Admin users only)
- `/claude <prompt>` - Send a prompt to Claude Code (supports multi-part messages)
- `/claude:new <prompt>` - Start a new session with a prompt
- `/claude:reset` - End session, kill stuck processes, and clear state
- `/claude:lock` - Enable locked mode (all messages route to Claude)
- `/claude:unlock` - Disable locked mode
- `/claude:sessions` - View and manage past sessions
- `/claude:help` - Show Claude command help
- `/meta <prompt>` - Execute Claude prompts in telegram_agent directory (for bot development)
- `/research <topic>` - Deep web research with multi-stage pipeline and Obsidian report
- `/session` - Show active session info
- `/session rename <name>` - Rename current session
- `/session list` - View all past sessions
- **Reply to Claude messages** - Continue in that specific session without commands

#### Collect Mode (Admin users only)
- `/collect:start` - Start collecting items for batch processing
- `/collect:go` - Process collected items with Claude
- `/collect:stop` - Stop collecting without processing
- `/collect:status` - Show what's been collected
- `/collect:clear` - Clear queue but stay in collect mode
- `/collect:help` - Show collect command help

#### Obsidian Notes
- `/note <name>` - View a note from the Obsidian vault
- Clickable `[[wikilinks]]` in messages open notes via deep links

#### User Settings
- `/settings` - Configure preferences (model selection, button visibility)

#### Spaced Repetition
- `/review` - Get next 5 cards due for review
- `/review <count>` - Get specific number of cards (e.g., `/review 10`)
- `/srs_stats` - View review statistics

### Image Analysis

1. Send any image to the bot
2. Bot will automatically:
   - Download and compress the image
   - Analyze using the current mode
   - Generate embeddings (if artistic mode)
   - Store results in database
   - Reply with analysis and similar images (if available)

### Collect Mode (Batch Processing)

Accumulate multiple items before processing them together with Claude:

1. Start collecting: `/collect:start`
2. Send items in any order:
   - Text messages
   - Images
   - Voice messages
   - Videos
3. Check status: `/collect:status` to see what's been collected
4. Process with Claude: `/collect:go` to send everything to Claude for analysis
5. Or cancel: `/collect:stop` to exit without processing

**Use cases**:
- Batch analyze multiple photos
- Transcribe several voice memos together
- Combine text notes, images, and voice for comprehensive analysis

### Reply Context System

The bot tracks message context to enable seamless conversation threading:

- **Reply to Claude**: Reply to any Claude Code response to continue in that exact session
- **Reply to transcriptions**: Reply to voice/video transcriptions to reference them
- **Session continuity**: Replying automatically resumes the correct Claude session
- **Works with locked mode**: Combine reply context with locked mode for natural conversations

### Claude Code Sessions

When using Claude Code, you get interactive AI assistance with session persistence:

1. Start with `/claude your question or task`
2. **Multi-part prompts**: Send additional messages within 2.5 seconds - they'll be combined:
   ```
   /claude Analyze this code
   <paste code here>
   Also check for security issues
   ```
   All three messages are combined into one prompt before Claude executes.

3. Claude responds with streaming output, showing tools being used:
   - **Read/Write/Edit**: File operations
   - **Bash**: Shell commands
   - **Skill**: Claude skills execution
   - **Task**: Background agent tasks
   - **WebFetch/WebSearch**: Web operations

4. Use inline buttons to:
   - **Reset**: End session and start fresh
   - **Continue**: Resume with a follow-up
   - **Lock/Unlock**: Toggle continuous mode
   - **Model**: Switch between Haiku/Sonnet/Opus

5. **Reply to continue sessions**: Reply to any Claude message to continue in that specific session
6. **Locked mode**: All text messages, voice messages, images, and videos route to Claude without `/claude` prefix
7. Sessions persist for 60 minutes of inactivity
8. Generated files (PDFs, images, audio, video) are automatically sent to you

### Web Admin Interface

Access the admin interface at `http://localhost:8000/admin`:

- User management (ban, unban, group assignment)
- Chat monitoring and message sending
- Bot statistics and analytics
- Real-time chat observation

## Development

### Project Structure

```
telegram_agent/
├── src/
│   ├── bot/              # Telegram bot handlers
│   │   ├── handlers/             # Command handlers (modular organization)
│   │   │   ├── core_commands.py      # /start, /help
│   │   │   ├── claude_commands.py    # /claude:* commands
│   │   │   ├── collect_commands.py   # /collect:* commands
│   │   │   ├── note_commands.py      # /note command
│   │   │   └── mode_commands.py      # /mode, /analyze, /coach
│   │   ├── message_handlers.py   # Message processing (text, images, voice, video)
│   │   ├── callback_handlers.py  # Inline button callbacks
│   │   ├── combined_processor.py # Combined message routing and buffering
│   │   └── bot.py                # Main bot initialization
│   ├── tunnel/           # Pluggable tunnel provider abstraction
│   │   ├── base.py                # TunnelProvider ABC
│   │   ├── factory.py             # get_tunnel_provider() factory
│   │   ├── ngrok_provider.py      # ngrok adapter (wraps NgrokManager)
│   │   ├── cloudflare_provider.py # Cloudflare Tunnel (named + quick)
│   │   └── tailscale_provider.py  # Tailscale Funnel
│   ├── api/              # FastAPI admin endpoints
│   ├── core/             # Business logic
│   ├── models/           # Database models
│   │   ├── chat.py               # Chat with claude_mode flag
│   │   ├── claude_session.py     # Claude session persistence
│   │   ├── admin_contact.py      # Admin users for Claude access
│   │   ├── collect_session.py    # Collect mode state
│   │   └── user.py               # User profiles
│   ├── services/         # External integrations
│   │   ├── claude_code_service.py  # Claude Code SDK integration
│   │   ├── message_buffer.py       # Message buffering for multi-part prompts
│   │   ├── reply_context.py        # Reply context tracking
│   │   ├── collect_service.py      # Collect mode batch processing
│   │   ├── voice_service.py        # Voice transcription
│   │   ├── vault_user_service.py   # Obsidian vault operations
│   │   └── ...
│   └── utils/            # Utilities
│       ├── completion_reactions.py # Emoji reactions for task completion
│       ├── session_emoji.py        # Session state emoji indicators
│       └── subprocess_helper.py    # Safe subprocess execution
├── config/               # YAML configurations
├── data/                 # Image storage and database
├── scripts/
│   ├── setup_wizard.py           # Interactive setup wizard entry point
│   ├── setup_wizard/             # Wizard steps and env manager
│   ├── start_dev.py              # Development server startup
│   ├── setup_webhook.py          # Webhook management
│   ├── health_check.sh           # Health monitoring script
│   ├── webhook_recovery.py       # Automatic webhook recovery
│   ├── daily_health_review.py    # Scheduled health review
│   ├── analyze_conversations.py  # Conversation analysis & patterns
│   └── proactive_tasks/          # Scheduled agent tasks
├── ops/
│   └── systemd/                  # systemd unit for Linux deployment
├── tests/                # Test suite (2400+ tests)
└── logs/                 # Application logs
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run only unit tests
pytest -m unit

# Run only integration tests  
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Code Quality

CI runs automatically on every push and pull request (lint, type check, tests, security scan).

```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/

# Security audit
pip-audit
detect-secrets scan

# Pre-commit hooks (recommended)
pre-commit install
pre-commit run --all-files
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Check current version
alembic current
```

## Scheduled Tasks

### Launchd Services

Four launchd services manage bot operations:

| Service | Plist | Schedule | Purpose |
|---------|-------|----------|---------|
| `bot` | `com.telegram-agent.bot` | Persistent | Main bot service |
| `health` | `com.telegram-agent.health` | Every 60s | Health monitoring + recovery |
| `daily-health-review` | `com.telegram-agent.daily-health-review` | 9:30am | Health summary |
| `daily-research` | `com.telegram-agent.daily-research` | 10:00am | AI research digest |

**SRS Services** (if SRS is configured):

| Service | Schedule | Purpose |
|---------|----------|---------|
| `com.telegram-agent.srs-sync` | Every hour | Sync vault with SRS database |
| `com.telegram-agent.srs-morning` | 9:00am | Send morning batch |

**Management:**
```bash
# Bot service
launchctl kickstart -k gui/$(id -u)/com.telegram-agent.bot

# Health monitor
launchctl list | grep telegram-agent

# SRS services
~/ai_projects/telegram_agent/scripts/srs_service.sh status
~/ai_projects/telegram_agent/scripts/srs_service.sh logs
```

### Proactive Task Framework

Register and run scheduled agent tasks:

```bash
# List all tasks
python -m scripts.proactive_tasks.task_runner list

# Run task manually
python -m scripts.proactive_tasks.task_runner run daily-research

# Generate and install launchd plist
python -m scripts.proactive_tasks.task_runner generate-plist daily-research --install
```

**Task registry:** `scripts/proactive_tasks/task_registry.yaml`

For detailed proactive task documentation, see [docs/FEATURES.md#proactive-task-framework](docs/FEATURES.md#proactive-task-framework).

## Monitoring & Auto-Recovery

The bot includes a robust health monitoring system that automatically detects and recovers from common issues.

### Health Check Service

A launchd service (`com.telegram-agent.health`) runs every 60 seconds and checks:

1. **Local service health**: Verifies the FastAPI server responds with healthy status
2. **Telegram webhook status**: Checks for webhook errors, URL mismatches, and pending updates

```bash
# Check health monitor status
launchctl list | grep telegram-agent.health

# View health logs
tail -f logs/launchd_health.log
tail -f logs/launchd_health.err

# Manual health check
PORT=8847 ENV_FILE=.env bash scripts/health_check.sh
```

### Automatic Webhook Recovery

When webhook issues are detected, the system attempts automatic recovery before restarting:

| Issue | Detection | Recovery Action |
|-------|-----------|-----------------|
| 401 Unauthorized | `last_error_message` contains "401" or "Unauthorized" | Re-register webhook with correct secret token |
| URL mismatch | Webhook URL doesn't match current tunnel URL | Update webhook to new tunnel URL |
| Webhook not set | Empty webhook URL | Set webhook with secret |
| High pending count | `pending_update_count > 10` | Re-register webhook to clear queue |

The recovery script (`scripts/webhook_recovery.py`) handles these automatically:

```bash
# Manual recovery (if needed)
ENV_FILE=.env python3 scripts/webhook_recovery.py

# Check current webhook status
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo" | python3 -m json.tool
```

### Recovery Flow

```
Health check (every 60s)
    │
    ├─ Local service unhealthy? ──────────────────────► Restart service
    │
    └─ Webhook error detected? ──► Run webhook_recovery.py
                                          │
                                          ├─ Success ──► Done (no restart)
                                          │
                                          └─ Failed ───► Restart service
```

### Service Configuration

Three launchd services manage the bot:

| Service | Plist | Purpose |
|---------|-------|---------|
| `com.telegram-agent.bot` | Bot service | Main Telegram bot |
| `com.telegram-agent.health` | Health monitor | Health checks every 60s |
| `com.telegram-agent.daily-health-review` | Daily review | Health summary at 9:30am |

```bash
# Restart bot service
launchctl kickstart -k gui/$(id -u)/com.telegram-agent.bot

# Reload health monitor after config changes
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.health.plist
launchctl load ~/Library/LaunchAgents/com.telegram-agent.health.plist
```

## Deployment

### Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f telegram-agent

# Stop services
docker-compose down
```

### Linux (systemd)

A systemd unit is provided for production deployment:

```bash
# Copy and configure the service
cp ops/systemd/telegram-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now telegram-agent
```

### Production Considerations

- Use PostgreSQL instead of SQLite for production
- Configure proper logging and monitoring
- Set up SSL/TLS for webhook endpoints
- Rate limiting and payload size limits are built in (`WEBHOOK_MAX_BODY_BYTES`, `WEBHOOK_RATE_LIMIT`)
- Use cloud storage for images (S3, etc.)
- Set up backup strategies for database and images

## API Documentation

Once running, visit:
- API docs: `http://localhost:8000/docs`
- Alternative docs: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

## MCP Integration

The bot supports MCP (Model Context Protocol) for extending capabilities:

1. Configure MCP servers in `config/mcp_servers.json`
2. Available tools are auto-discovered
3. LLM can call tools during image analysis
4. Results are incorporated into responses

## Troubleshooting

### Common Issues

1. **Webhook not receiving updates**:
   - The health monitor auto-recovers most webhook issues within 60 seconds
   - Check tunnel is running (ngrok: `curl -s http://127.0.0.1:4040/api/tunnels`, cloudflare: check `logs/cloudflared.log`, tailscale: `tailscale status`)
   - Manual recovery: `ENV_FILE=.env python3 scripts/webhook_recovery.py`
   - Check webhook status: `curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo" | python3 -m json.tool`
   - Common causes: tunnel URL changed, secret token mismatch, service restart

2. **Image processing fails**:
   - Verify OpenAI API key and credits
   - Check network connectivity
   - Review logs in `logs/app.log`

3. **Database errors**:
   - Check database file permissions
   - Run `alembic upgrade head` to apply migrations
   - Verify DATABASE_URL is correct

4. **Mode switching not working**:
   - Validate `config/modes.yaml` syntax
   - Check chat exists in database
   - Review mode configuration

5. **Claude Code session issues**:
   - Sessions expire after 60 minutes of inactivity
   - Use `/reset` to clear stuck sessions
   - Check admin_contacts table for authorized users
   - Claude uses Anthropic subscription (not API key)
   - Timeout is 5 minutes per query

6. **Claude locked mode not working**:
   - Verify user is in admin_contacts table
   - Check `claude_mode` flag in chats table
   - Use `/claude:unlock` to disable if stuck
   - In locked mode, ALL messages (text, voice, images, video) route to Claude without `/claude` prefix

7. **SRS cards not appearing**:
   - Check database: `sqlite3 data/srs/schedule.db "SELECT COUNT(*) FROM srs_cards;"`
   - Verify sync service: `~/ai_projects/telegram_agent/scripts/srs_service.sh status`
   - Check logs: `~/ai_projects/telegram_agent/scripts/srs_service.sh logs`
   - Re-seed vault: `python src/services/srs/srs_sync.py -v`

8. **Session naming not working**:
   - Sessions are auto-named after first response
   - Use `/session rename <name>` to manually rename
   - Check logs for "Generating session name" entries

### Debug Commands

```bash
# Check database content
sqlite3 data/telegram_agent.db ".tables"
sqlite3 data/telegram_agent.db "SELECT * FROM chats LIMIT 5;"

# Check Claude sessions
sqlite3 data/telegram_agent.db "SELECT session_id, chat_id, is_active, last_used FROM claude_sessions ORDER BY last_used DESC LIMIT 5;"

# Check admin contacts
sqlite3 data/telegram_agent.db "SELECT chat_id, name, active FROM admin_contacts;"

# Check claude_mode status
sqlite3 data/telegram_agent.db "SELECT chat_id, claude_mode FROM chats WHERE claude_mode = 1;"

# Test image processing
python -c "from src.core.image_processor import process_image; print(process_image('tests/fixtures/test.jpg'))"

# Validate configuration
python -c "from src.core.config import get_settings; print(get_settings())"

# Kill stuck Claude processes
pgrep -f "claude.*--resume" | xargs kill
```

## Documentation

### Feature Documentation

This README covers quick start and common commands. For comprehensive feature documentation, see:

- **[docs/FEATURES.md](docs/FEATURES.md)** - Complete feature reference with detailed examples
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture overview
- **[docs/dev-setup-shell.md](docs/dev-setup-shell.md)** - Interactive & manual setup guide
- **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)** - Development guide
- **[docs/PLUGINS.md](docs/PLUGINS.md)** - Plugin development
- **[docs/SRS_INTEGRATION.md](docs/SRS_INTEGRATION.md)** - SRS technical details
- **[docs/DESIGN_SKILLS.md](docs/DESIGN_SKILLS.md)** - Design skills guide
- **[scripts/README.md](scripts/README.md)** - Scripts & development tools reference
- **[CHANGELOG.md](CHANGELOG.md)** - Recent changes

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run quality checks: `black`, `flake8`, `mypy`, `pytest`
5. Submit a pull request

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for detailed development guidelines.

## License

[MIT License](LICENSE)

## Support

- Create an issue for bug reports
- Check existing issues for solutions
- Review `CLAUDE.md` for development guidelines
