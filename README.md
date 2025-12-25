# Telegram Agent v0.5

A Telegram bot with advanced image processing, vision AI analysis, Claude Code SDK integration, and web admin interface. Supports multiple analysis modes, vector similarity search, interactive AI sessions, message buffering, and scheduled automations.

## Features

### Core Features
- **Image Processing Pipeline**: Download, compress, analyze, and store images with AI-powered analysis
- **Multiple Analysis Modes**: Default (quick description) and Artistic (in-depth analysis with presets)
- **Vector Similarity Search**: Find similar images using embeddings (artistic mode)
- **Web Admin Interface**: User management, chat monitoring, and bot statistics
- **MCP Integration**: Auto-discovery and execution of MCP tools
- **Background Processing**: Async image analysis and embedding generation

### Claude Code SDK Integration
- **Interactive AI Sessions**: Full Claude Code SDK integration with streaming responses
- **Session Persistence**: Sessions are stored and can be resumed across conversations
- **Claude Locked Mode**: Toggle continuous conversation mode without `/claude` prefix
- **Session Controls**: Inline keyboard buttons for Reset, Continue, and Lock/Unlock
- **Tool Display**: Real-time display of Claude's actions (Read, Write, Bash, Skills, Tasks, Web searches)
- **Auto-send Files**: Generated files (PDF, images, audio, video) are automatically sent to users
- **Long Message Handling**: Automatic splitting of responses exceeding Telegram limits

### Message Buffering System
- **Multi-part Prompts**: Send `/claude` followed by multiple messages - all are combined into one prompt
- **Smart Combining**: Buffer waits 2.5 seconds after last message before executing
- **Media Support**: Combine text, images, voice messages, and documents in a single request
- **Reply Context**: Reply to Claude's messages to continue in the same session

### Obsidian Integration
- **Wikilinks Support**: Clickable `[[wikilinks]]` with deep link navigation
- **Note Viewing**: View Obsidian notes directly in Telegram via deep links
- **Vault Operations**: Read, search, and edit notes through Claude sessions

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
- `/c <prompt>` - Alias for `/claude`
- `/continue` or `/cont` - Continue the current session
- `/reset` - End current session and start fresh
- `/sessions` - View and manage past sessions
- `/lock` - Enable Claude locked mode (all messages go to Claude)
- `/unlock` - Disable Claude locked mode
- `/model <haiku|sonnet|opus>` - Change the Claude model for this chat

### Image Analysis

1. Send any image to the bot
2. Bot will automatically:
   - Download and compress the image
   - Analyze using the current mode
   - Generate embeddings (if artistic mode)
   - Store results in database
   - Reply with analysis and similar images (if available)

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

5. In locked mode, all messages go directly to Claude without `/claude` prefix
6. Sessions persist for 60 minutes of inactivity
7. Generated files (PDFs, images, audio, video) are automatically sent to you
8. Reply to Claude's messages to continue in that specific session

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
│   │   ├── handlers.py           # Command handlers
│   │   ├── message_handlers.py   # Message processing
│   │   ├── callback_handlers.py  # Inline button callbacks
│   │   ├── combined_processor.py # Combined message routing
│   │   └── keyboard_utils.py     # Inline keyboard builders
│   ├── api/              # FastAPI admin endpoints
│   ├── core/             # Business logic
│   ├── models/           # Database models
│   │   ├── chat.py               # Chat with claude_mode flag
│   │   ├── claude_session.py     # Claude session persistence
│   │   └── admin_contact.py      # Admin users for Claude access
│   ├── services/         # External integrations
│   │   ├── claude_code_service.py  # Claude Code SDK integration
│   │   ├── message_buffer.py       # Message buffering for multi-part prompts
│   │   ├── reply_context.py        # Reply context tracking
│   │   └── ...
│   └── utils/            # Utilities
├── config/               # YAML configurations
├── data/                 # Image storage and database
├── scripts/
│   ├── start_dev.py              # Development server startup
│   ├── setup_webhook.py          # Webhook management
│   └── daily_health_review.py    # Scheduled health review
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
   - Check ngrok is running and URL is correct
   - Verify bot token is valid
   - Check webhook status: `curl -X GET "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"`

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
   - Use `/unlock` to disable if stuck

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