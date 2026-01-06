# Telegram Agent v0.7

A Telegram bot with advanced image processing, vision AI analysis, Claude Code SDK integration, and web admin interface. Features intelligent reply context tracking, batch processing, voice/video transcription, Obsidian vault integration, multi-part message buffering, and automated health monitoring.

## Features

### Core Features
- **Image Processing Pipeline**: Download, compress, analyze, and store images with AI-powered analysis
- **Multiple Analysis Modes**: Default (quick description) and Artistic (in-depth analysis with presets)
- **Vector Similarity Search**: Find similar images using embeddings (artistic mode)
- **Web Admin Interface**: User management, chat monitoring, and bot statistics
- **MCP Integration**: Auto-discovery and execution of MCP tools
- **Background Processing**: Async image analysis and embedding generation
- **Graceful Shutdown**: Background tasks are tracked and properly cancelled on shutdown
- **Centralized Configuration**: All settings managed via pydantic-settings with env var support

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

### Message Buffering System
- **Multi-part Prompts**: Send `/claude` followed by multiple messages - all are combined into one prompt
- **Smart Combining**: Buffer waits 2.5 seconds after last message before executing
- **Media Support**: Combine text, images, voice messages, and documents in a single request
- **Voice & Video Transcription**: Automatically transcribe voice/video messages and optionally route to Claude

### Obsidian Integration
- **Wikilinks Support**: Clickable `[[wikilinks]]` with deep link navigation
- **Note Viewing**: View Obsidian notes directly in Telegram via `/note` command and deep links
- **Vault Operations**: Read, search, and edit notes through Claude sessions

### Batch Processing
- **Collect Mode**: Accumulate multiple messages, images, voice memos, or videos before processing
- **Batch Claude Processing**: Send collected items together to Claude for comprehensive analysis
- **Queue Management**: View, clear, or cancel collection without processing

### Scheduled Automations
- **Daily Health Review**: Automated health data summary sent at 9:30am via launchd
- **launchd Service**: System service configuration for reliable background operation

### Admin Features
- **Admin Contacts**: Manage authorized users for Claude Code access
- **Messaging API**: Send messages programmatically to admin contacts

## Quick Start

### Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key (or other LLM provider)
- ngrok (for local webhook development)
- Claude Code SDK (for AI session integration): `pip install claude-code-sdk`
- Anthropic subscription (Claude Code uses subscription, not API credits)

### Installation

1. Clone and setup:
```bash
git clone <repository-url>
cd telegram_agent
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
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
# In one terminal - start the FastAPI server
python -m uvicorn src.main:app --reload --port 8000

# In another terminal - start ngrok tunnel
ngrok http 8000

# Copy the ngrok URL and update TELEGRAM_WEBHOOK_URL in .env.local
# Then set the webhook:
python -m src.bot.setup_webhook
```

## Configuration

### Environment Variables

See `.env.example` for all available configuration options.

Key variables:
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `OPENAI_API_KEY`: OpenAI API key for vision analysis
- `DATABASE_URL`: SQLite database path
- `TELEGRAM_WEBHOOK_URL`: ngrok URL for webhook

Claude Code integration:
- `CLAUDE_CODE_WORK_DIR`: Working directory for Claude (default: `~/Research/vault`)
- `CLAUDE_CODE_MODEL`: Default model (`sonnet`, `opus`, `haiku`)

Scheduled tasks:
- Configure `launchd` for daily health reviews (see `scripts/daily_health_review.py`)

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
│   ├── start_dev.py              # Development server startup
│   ├── setup_webhook.py          # Webhook management
│   ├── health_check.sh           # Health monitoring script
│   ├── webhook_recovery.py       # Automatic webhook recovery
│   ├── daily_health_review.py    # Scheduled health review
│   └── weekly_health_report.py   # Weekly health analytics
├── tests/                # Test suite
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

```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/

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

### Daily Health Review

The bot can send automated health summaries via the `daily_health_review.py` script.

1. Configure your health data source in the script
2. Set up launchd for scheduling:

```bash
# Create launchd plist in ~/Library/LaunchAgents/
# See scripts/daily_health_review.py for launchd configuration example

# Load the scheduled task
launchctl load ~/Library/LaunchAgents/com.telegram-agent.health-review.plist

# Verify it's running
launchctl list | grep telegram-agent
```

The health review runs at 9:30am daily and sends a summary to configured chat IDs.

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
| URL mismatch | Webhook URL doesn't match current ngrok URL | Update webhook to new ngrok URL |
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

### Production Considerations

- Use PostgreSQL instead of SQLite for production
- Configure proper logging and monitoring
- Set up SSL/TLS for webhook endpoints
- Implement rate limiting and security measures
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
   - Check ngrok is running: `curl -s http://127.0.0.1:4040/api/tunnels`
   - Manual recovery: `ENV_FILE=.env python3 scripts/webhook_recovery.py`
   - Check webhook status: `curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo" | python3 -m json.tool`
   - Common causes: ngrok URL changed, secret token mismatch, service restart

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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run quality checks: `black`, `flake8`, `mypy`, `pytest`
5. Submit a pull request

## License

[MIT License](LICENSE)

## Support

- Create an issue for bug reports
- Check existing issues for solutions
- Review `CLAUDE.md` for development guidelines