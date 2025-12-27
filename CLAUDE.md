# Claude Development Instructions

## Project Overview
This is a Telegram bot with image processing capabilities, vision AI analysis, and web admin interface. The project uses FastAPI, python-telegram-bot, SQLite with vector search, and MCP integration.

## Development Workflow

### Before Making Changes
1. **Always run linting and fix errors before building**
2. **Run tests to ensure nothing is broken**
3. **Update this CLAUDE.md file if new commands or patterns are discovered**
4. **ALWAYS LOG EVERYTHING YOU DO TO A FILE** - Use structured logging to track all actions, decisions, and changes

### Production: Launchd Service
The bot runs as a launchd service in production. **After code changes, restart the service:**

```bash
# Restart bot to apply code changes
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist && \
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist

# Check status
launchctl list | grep telegram

# View logs
tail -f logs/app.log
```

Service files:
- `~/Library/LaunchAgents/com.telegram-agent.bot.plist` - Main bot service
- `~/Library/LaunchAgents/com.telegram-agent.health.plist` - Health monitor
- `~/Library/LaunchAgents/com.telegram-agent.daily-health-review.plist` - Daily review

### Commands to Run
```bash
# ⭐ START THE BOT (preferred method - includes ngrok + webhook setup)
/opt/homebrew/bin/python3.11 scripts/start_dev.py start --port 8000

# Linting and formatting
python -m black src/ tests/
python -m flake8 src/ tests/
python -m isort src/ tests/

# Type checking
python -m mypy src/

# Testing
python -m pytest tests/ -v
python -m pytest tests/ --cov=src --cov-report=html

# Running server only (no ngrok/webhook - for testing)
/opt/homebrew/bin/python3.11 -m uvicorn src.main:app --reload --port 8000

# Webhook management
python scripts/setup_webhook.py auto-update --port 8000
python scripts/setup_webhook.py get-webhook
python scripts/setup_webhook.py validate-bot

# Database migrations (if using Alembic)
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Project Structure
```
telegram_agent/
├── src/
│   ├── bot/                 # Telegram bot handlers and commands
│   │   ├── __init__.py
│   │   ├── bot.py           # Bot initialization and setup
│   │   ├── handlers.py      # Command handlers (/claude, /reset, etc.)
│   │   ├── message_handlers.py   # Text/media message handling
│   │   ├── callback_handlers.py  # Inline keyboard callbacks
│   │   ├── combined_processor.py # Routes combined buffered messages
│   │   └── keyboard_utils.py     # Inline keyboard builders
│   ├── api/                 # FastAPI endpoints
│   │   ├── __init__.py
│   │   ├── admin.py         # Admin interface endpoints
│   │   ├── bot.py           # Bot webhook endpoints
│   │   └── health.py        # Health check endpoints
│   ├── core/                # Business logic
│   │   ├── __init__.py
│   │   ├── config.py        # Configuration management
│   │   ├── database.py      # Database connection and setup
│   │   ├── image_processor.py # Image processing pipeline
│   │   ├── mode_manager.py  # Mode switching logic
│   │   └── mcp_client.py    # MCP integration
│   ├── models/              # Database models
│   │   ├── __init__.py
│   │   ├── chat.py          # Chat model (with claude_mode flag)
│   │   ├── claude_session.py # Claude session persistence
│   │   ├── admin_contact.py # Admin users for Claude access
│   │   ├── image.py         # Image model
│   │   └── user.py          # User model
│   ├── services/            # External service integrations
│   │   ├── __init__.py
│   │   ├── claude_code_service.py # Claude Code SDK integration
│   │   ├── message_buffer.py     # Message buffering for multi-part prompts
│   │   ├── reply_context.py      # Reply context tracking
│   │   ├── llm_service.py        # LiteLLM integration
│   │   ├── telegram_service.py   # Telegram API wrapper
│   │   └── vector_service.py     # Vector similarity search
│   ├── utils/               # Utilities
│   │   ├── __init__.py
│   │   ├── image_utils.py   # Image processing helpers
│   │   ├── logging.py       # Logging configuration
│   │   ├── ngrok_utils.py   # ngrok tunnel management
│   │   ├── task_tracker.py  # Background task tracking for graceful shutdown
│   │   └── validators.py    # Input validation
│   └── main.py              # FastAPI application entry point
├── config/
│   ├── modes.yaml           # Mode and preset definitions
│   ├── ngrok.yml            # ngrok tunnel configuration
│   └── settings.yaml        # Application settings
├── data/
│   ├── raw/                 # Original images
│   ├── img/                 # Compressed images
│   └── telegram_agent.db    # SQLite database
├── tests/
│   ├── conftest.py          # Pytest configuration
│   ├── fixtures/            # Test images and data
│   ├── test_bot/            # Bot handler tests
│   ├── test_core/           # Core logic tests
│   └── test_api/            # API endpoint tests
├── scripts/
│   ├── start_dev.py         # Development environment startup
│   ├── setup_webhook.py     # Webhook management utility
│   └── daily_health_review.py # Scheduled health review
├── logs/                    # Application logs
│   ├── app.log              # Main application log
│   └── errors.log           # Error-only log
├── requirements.txt
├── .env.example
├── .gitignore
├── pytest.ini
├── pyproject.toml           # Tool configuration
├── docker-compose.yml
└── README.md
```

### Key Components

#### Image Processing Pipeline
1. **Download**: `src/core/image_processor.py:download_image()`
2. **Compress**: `src/core/image_processor.py:compress_image()`
3. **Analyze**: `src/services/llm_service.py:analyze_image()`
4. **Embed**: `src/services/vector_service.py:generate_embedding()`
5. **Store**: `src/models/image.py:save_analysis()`

#### Message Buffering System
The bot uses a message buffer to combine multi-part messages before processing:

1. **MessageBuffer** (`src/services/message_buffer.py`):
   - Collects messages per (chat_id, user_id) pair
   - 2.5 second timeout after last message
   - Supports text, images, voice, documents, contacts
   - Special handling for `/claude` commands

2. **CombinedMessageProcessor** (`src/bot/combined_processor.py`):
   - Routes combined messages based on content type
   - Handles `/claude` commands with combined prompts
   - Runs Claude execution in background tasks (avoids blocking)

3. **ReplyContext** (`src/services/reply_context.py`):
   - Tracks message origins for reply handling
   - Enables "reply to continue" functionality

**Flow**:
```
User sends /claude prompt → Buffer collects
User sends more text     → Buffer adds to collection
2.5s timeout             → Buffer flushes
CombinedMessageProcessor → Routes to Claude
Background task          → Executes Claude prompt
```

#### Claude Code Integration
- Service: `src/services/claude_code_service.py`
- Session persistence in database
- In-memory session cache for fast lookups
- Background task execution to avoid webhook blocking
- Auto-send generated files to users

#### Mode System
- Configuration in `config/modes.yaml`
- Logic in `src/core/mode_manager.py`
- Database persistence in `src/models/chat.py`

#### MCP Integration
- Client setup in `src/core/mcp_client.py`
- Auto-discovery of available tools
- Tool calling from LLM responses

#### ngrok Integration
- Tunnel management in `src/utils/ngrok_utils.py`
- Webhook API endpoints in `src/api/webhook.py`
- Development scripts in `scripts/` for automated setup

### Environment Variables
Required in `.env.local` or `.env`:
```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_URL=https://your-ngrok-url.ngrok.io/webhook
TELEGRAM_WEBHOOK_SECRET=your_webhook_secret_here

# OpenAI (or other LLM providers)
OPENAI_API_KEY=your_openai_key
LITELLM_LOG=DEBUG

# ngrok Configuration
NGROK_AUTHTOKEN=your_ngrok_authtoken_here
NGROK_AUTO_UPDATE=true
NGROK_PORT=8000
NGROK_REGION=us
NGROK_TUNNEL_NAME=telegram-agent

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/telegram_agent.db

# Application
DEBUG=true
LOG_LEVEL=INFO
```

### Database Operations
- **Models**: SQLAlchemy ORM models in `src/models/`
- **Migrations**: Use Alembic for schema changes
- **Vector Search**: sqlite-vss for similarity search

### Testing Strategy
- **Unit Tests**: Mock external APIs (Telegram, OpenAI)
- **Integration Tests**: Test complete workflows with test fixtures
- **Test Images**: Store in `tests/fixtures/`
- **Coverage**: Aim for >80% code coverage

### Code Style
- **Formatting**: Black with 88 character line limit
- **Imports**: isort for import sorting
- **Type Hints**: Use throughout, check with mypy
- **Docstrings**: Google style docstrings for public methods

### Common Patterns

#### Comprehensive Logging (MANDATORY)
```python
import logging
import structlog
from typing import Optional

# Always use structured logging to track all actions
logger = structlog.get_logger(__name__)

async def process_image(file_path: str) -> Optional[dict]:
    logger.info("Starting image processing", file_path=file_path)
    try:
        # Log each major step
        logger.info("Downloading image", file_path=file_path)
        # Processing logic
        logger.info("Image processing completed successfully", 
                   file_path=file_path, result_keys=list(result.keys()))
        return result
    except Exception as e:
        logger.error("Image processing failed", 
                    file_path=file_path, error=str(e), exc_info=True)
        return None
```

#### Error Handling
```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def process_image(file_path: str) -> Optional[dict]:
    try:
        # Processing logic
        return result
    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        return None
```

#### Configuration Access
```python
from src.core.config import get_settings

settings = get_settings()
api_key = settings.openai_api_key
python_path = settings.python_executable  # Platform-independent Python path
```

#### Background Task Tracking
Use `create_tracked_task()` instead of `asyncio.create_task()` for graceful shutdown:
```python
from src.utils.task_tracker import create_tracked_task

# BAD - task is orphaned on shutdown:
asyncio.create_task(run_claude())

# GOOD - task is tracked and cancelled gracefully:
create_tracked_task(run_claude(), name="claude_execution")
```

#### Database Operations
```python
from src.core.database import get_db_session
from src.models.image import Image

async def save_image_analysis(chat_id: int, analysis: dict):
    async with get_db_session() as session:
        image = Image(chat_id=chat_id, analysis=analysis)
        session.add(image)
        await session.commit()
```

### Debugging
- **Logs**: Structured JSON logging to `logs/app.log`
- **Database**: Use `sqlite3` CLI or DB browser
- **Telegram**: Use webhook URL with ngrok for local development
- **LLM Calls**: Enable LiteLLM debug logging

### Performance Considerations
- **Image Processing**: Resize before analysis to save on API costs
- **Background Jobs**: Use async tasks for heavy operations
- **Caching**: Cache embeddings and analysis results
- **Rate Limiting**: Respect API rate limits

### Security Notes
- **API Keys**: Never commit to repository
- **User Data**: Handle Telegram user data according to privacy policy
- **Image Storage**: Consider encryption for sensitive images
- **Admin Access**: Implement proper authentication for web admin

### Deployment Notes
- **Local Development**: Use ngrok for webhook testing
- **Database**: SQLite for development, consider PostgreSQL for production
- **File Storage**: Local filesystem for development, consider cloud storage for production
- **Background Jobs**: In-process async tasks for development, consider Celery for production

### Troubleshooting

#### Common Issues
1. **Webhook not receiving updates**: Check ngrok URL and bot token
2. **Image processing fails**: Verify API keys and network connectivity
3. **Database locked**: Check for hanging transactions
4. **Mode switching not working**: Verify YAML config syntax
5. **Message combining not working**:
   - Messages must arrive within 2.5 seconds of each other
   - Check `logs/app.log` for "Buffered" and "Flushing buffer" entries
6. **Claude execution blocking/hanging**:
   - Claude execution runs in background task to avoid blocking
   - Use in-memory session cache (database lookups can cause deadlocks during buffer processing)
   - Check `logs/errors.log` for database timeout errors

#### Debug Commands
```bash
# Check webhook status
curl -X GET "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Test image processing
python -c "from src.core.image_processor import process_image; print(process_image('tests/fixtures/test.jpg'))"

# Check database
sqlite3 data/telegram_agent.db ".tables"
sqlite3 data/telegram_agent.db "SELECT * FROM chats LIMIT 5;"

# Check Claude sessions
sqlite3 data/telegram_agent.db "SELECT session_id, chat_id, is_active, last_used FROM claude_sessions ORDER BY last_used DESC LIMIT 5;"

# Check admin contacts
sqlite3 data/telegram_agent.db "SELECT chat_id, name, active FROM admin_contacts;"

# Watch logs in real-time
tail -f logs/app.log

# Check for message buffering
grep -E "Buffered|Flushing|combined" logs/app.log | tail -20
```

#### Known Limitations

##### CRITICAL: Async Blocking in uvicorn + telegram-bot Context
The bot runs inside uvicorn with python-telegram-bot. This creates an event loop context where certain async operations **block indefinitely** even though they work fine in standalone `asyncio.run()`:

**Operations that BLOCK in bot context:**
1. `context.bot.get_file()` - Telegram file downloads
2. `context.bot.send_message()` / `message.edit_text()` - Telegram API calls
3. Claude Code SDK `query()` function - especially with image prompts
4. `httpx.AsyncClient` requests - including Groq transcription API

**Solution: Use subprocess for ALL external I/O:**
```python
# BAD - will block in bot context:
file = await bot.get_file(file_id)
await file.download_to_drive(path)

# GOOD - use subprocess with config-based Python path:
from src.core.config import get_settings

script = f'''
import requests
r = requests.get(f"https://api.telegram.org/bot{{token}}/getFile?file_id={{file_id}}")
# ... download file
'''
python_path = get_settings().python_executable
subprocess.run([python_path, "-c", script], ...)
```

**Files implementing subprocess workarounds:**
- `src/services/claude_subprocess.py` - Claude SDK execution
- `src/bot/combined_processor.py` - Image/voice downloads, transcription
- `src/bot/handlers.py` - `send_message_sync()`, `edit_message_sync()`

**Always use tracked background tasks for Claude execution:**
```python
from src.utils.task_tracker import create_tracked_task

# BAD - blocks webhook:
await execute_claude_prompt(update, context, prompt)

# GOOD - runs in background with graceful shutdown support:
create_tracked_task(run_claude(), name="claude_execution")
```

##### Other Limitations
- **Database deadlocks during buffer processing**: The message buffer runs in an async timer callback. Database operations from this context can deadlock with SQLite. Solution: Use in-memory caches for session lookups, run Claude execution in background tasks.
- **2.5 second buffer timeout**: Fixed timeout may feel slow for quick single messages. This is a trade-off for combining multi-part prompts.

### Git Workflow
- **Branch naming**: feature/description or fix/description
- **Commit messages**: Use conventional commits format
- **Before committing**: Run linting, type checking, and tests
- **Pull requests**: Include test coverage and documentation updates

Remember: Always run linting and fix errors before building!