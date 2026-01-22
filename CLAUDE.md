# Claude Development Instructions

## Tech Stack

### Core Technologies
- **Python 3.11+** - Primary language
- **FastAPI** - Web framework for webhook and admin API
- **python-telegram-bot 21.x** - Telegram Bot API wrapper
- **SQLAlchemy 2.x** - Async ORM for database
- **SQLite** - Database with vector search extensions (sqlite-vss)
- **LiteLLM** - Unified LLM API (OpenAI, Anthropic, etc.)
- **Claude Code SDK** - Interactive AI sessions

### Key Libraries
- **Groq Whisper** - Voice/video transcription
- **PIL/Pillow** - Image processing
- **pydantic-settings** - Configuration management
- **structlog** - Structured logging
- **pytest** - Testing framework

### External Services
- **ngrok** - Local webhook tunnel (development)
- **Telegram Bot API** - Message delivery
- **Anthropic API** - Claude Code (subscription-based)
- **OpenAI API** - Image analysis, embeddings
- **Groq API** - Audio transcription

### Architecture Patterns
- **Subprocess isolation** - Avoid async blocking in nested event loops
- **Background task tracking** - Graceful shutdown with `create_tracked_task()`
- **Message buffering** - Combine multi-part messages (2.5s timeout)
- **Plugin system** - Extensible architecture with lifecycle hooks
- **Service container** - Dependency injection for services

## Project Overview
This is a Telegram bot with advanced Claude Code integration, image processing, voice/video transcription, Obsidian vault operations, and spaced repetition system. The project uses FastAPI, python-telegram-bot, SQLite with vector search, and a modular plugin architecture.

### Key Capabilities
- **🤖 Claude Code Integration**: Interactive AI sessions with streaming, session persistence, auto-naming
- **📚 Spaced Repetition System**: SM-2 algorithm for vault idea review with scheduled batches
- **🎨 Design Skills**: Automatic UI/UX guidance from Impeccable Style, UI Skills, Rams.ai
- **🎤 Voice & Video**: Groq Whisper transcription with LLM correction, auto-route to Claude
- **📝 Obsidian Vault**: Read/edit notes, clickable wikilinks, deep link navigation
- **🗂️ Batch Processing**: Collect mode for accumulating items before processing
- **💬 Smart Buffering**: Combine multi-part messages with reply context tracking
- **⚙️ Plugin System**: Extensible architecture (claude_code, pdf plugins included)
- **🔧 Production Ready**: Launchd services, health monitoring, auto-recovery, comprehensive logging

**Documentation:**
- [Architecture Overview](docs/ARCHITECTURE.md) - System design, message flow, layer architecture
- [Contributing Guide](docs/CONTRIBUTING.md) - Development setup, code style, plugin creation
- [SRS Integration](docs/SRS_INTEGRATION.md) - Spaced repetition system details
- [Design Skills](docs/DESIGN_SKILLS.md) - UI/UX guidance integration
- [Quick Reference](docs/QUICKREF.md) - Essential commands and patterns
- [Changelog](CHANGELOG.md) - Recent features and changes

## Development Workflow

## Quick Start for Developers

Get from zero to first contribution in 10 minutes:

### 1. Clone and Setup (2 min)
```bash
git clone <repo-url>
cd telegram_agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env.local
```

### 2. Configure Environment (3 min)
Edit `.env.local`:
```bash
# Required
TELEGRAM_BOT_TOKEN=get_from_botfather
OPENAI_API_KEY=for_image_analysis
GROQ_API_KEY=for_voice_transcription

# Optional for full features
ANTHROPIC_API_KEY=for_claude_code
OBSIDIAN_VAULT_PATH=/path/to/vault
```

### 3. Initialize Database (1 min)
```bash
python -m src.core.database init
```

### 4. Start Development Server (1 min)
```bash
python scripts/start_dev.py start --port 8000
```
This auto-starts:
- FastAPI server on port 8000
- ngrok tunnel with auto-webhook setup
- Background health monitoring

### 5. Verify Setup (1 min)
```bash
# Send a message to your bot in Telegram
# Check logs
tail -f logs/app.log

# Check health
curl http://localhost:8000/health
```

### 6. Make Your First Change (2 min)
```bash
# Edit code
# Run linting
black src/ tests/
flake8 src/ tests/

# Run tests
pytest tests/ -v

# Restart bot to apply changes
launchctl kickstart -k gui/$(id -u)/com.telegram-agent.bot
```

### Key Development Files
- `src/bot/handlers/` - Command handlers (start here for new commands)
- `src/services/` - Business logic (start here for new features)
- `config/modes.yaml` - Bot modes and presets
- `tests/` - Test suite (add tests for your changes)

### Development Tips
- **Always lint before committing**: `black . && flake8 . && mypy src/`
- **Use subprocess helpers**: See `src/utils/subprocess_helper.py` for async patterns
- **Track background tasks**: Use `create_tracked_task()` for graceful shutdown
- **Log everything**: Use structlog for comprehensive logging

### Common Development Tasks
```bash
# Run single test file
pytest tests/test_services/test_claude_code_service.py -v

# Run with coverage
pytest --cov=src --cov-report=html

# Check webhook status
python scripts/setup_webhook.py get-webhook

# View bot logs in real-time
tail -f logs/app.log

# Check Claude sessions
sqlite3 data/telegram_agent.db "SELECT * FROM claude_sessions;"
```

### Next Steps
1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) to understand the system
2. Review [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for code style guidelines
3. Check [docs/PLUGINS.md](docs/PLUGINS.md) if building a plugin
4. See [FEATURES.md](FEATURES.md) for feature documentation

### Before Making Changes
1. **Always run linting and fix errors before building**
2. **Run tests to ensure nothing is broken**
3. **Update this CLAUDE.md file if new commands or patterns are discovered**
4. **ALWAYS LOG EVERYTHING YOU DO TO A FILE** - Use structured logging to track all actions, decisions, and changes

### Production: Launchd Service
The bot runs as a launchd service. **After code changes, restart the service:**

```bash
# Restart bot to apply code changes
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist && \
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist

# Wait for startup and verify
sleep 5 && launchctl list | grep telegram && tail -10 logs/app.log
```

**IMPORTANT - Restart Flow:**
1. The restart script (`scripts/run_agent_launchd.sh`) automatically:
   - Kills existing ngrok processes
   - Starts a new ngrok tunnel (new URL each time)
   - Sets webhook with secret token AND `drop_pending_updates=true`
   - Starts uvicorn on port 8847

2. **If you see "Invalid webhook secret token" errors after restart:**
   - This means old Telegram updates are arriving without the correct secret
   - The script now sets `drop_pending_updates=true` to prevent this
   - If it still happens, manually clear pending updates:
   ```bash
   source .env && curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=&drop_pending_updates=true"
   ```

3. **Verify webhook is correctly configured:**
   ```bash
   source .env && curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
   ```

Service files:
- `~/Library/LaunchAgents/com.telegram-agent.bot.plist` - Main bot service
- `~/Library/LaunchAgents/com.telegram-agent.health.plist` - Health monitor
- `~/Library/LaunchAgents/com.telegram-agent.daily-health-review.plist` - Daily health review (9:30 AM)
- `~/Library/LaunchAgents/com.telegram-agent.daily-research.plist` - Daily research (10:00 AM)

### Proactive Task Management
The bot includes a proactive task framework for managing scheduled agent tasks.

```bash
# List all registered tasks
python -m scripts.proactive_tasks.task_runner list

# Run a task manually
python -m scripts.proactive_tasks.task_runner run daily-research

# Dry-run (show what would be done)
python -m scripts.proactive_tasks.task_runner run daily-research --dry-run

# Generate and install launchd plist
python -m scripts.proactive_tasks.task_runner generate-plist daily-research --install

# Activate a task schedule
launchctl load ~/Library/LaunchAgents/com.telegram-agent.daily-research.plist
```

**Task Registry:** `scripts/proactive_tasks/task_registry.yaml`
- Configure topics, schedules, and output settings
- Add new tasks by creating a class that extends `BaseTask`

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

# SRS Management
python src/services/srs/srs_sync.py -v                    # Sync vault
python src/services/srs/srs_algorithm.py --due --limit 10 # Check due cards
~/ai_projects/telegram_agent/scripts/srs_service.sh status # Check services

# Design Skills Management
python scripts/manage_design_skills.py show               # View config
python scripts/manage_design_skills.py test "your prompt" # Test detection
python scripts/manage_design_skills.py review             # Get checklist

# Proactive Tasks
python -m scripts.proactive_tasks.task_runner list        # List tasks
python -m scripts.proactive_tasks.task_runner run task-name # Run task
```

### Project Structure
```
telegram_agent/
├── src/
│   ├── bot/                 # Telegram bot handlers and commands
│   │   ├── __init__.py
│   │   ├── bot.py           # Bot initialization and setup
│   │   ├── handlers/        # Modular command handlers (NEW)
│   │   │   ├── base.py          # Base handler class
│   │   │   ├── core_commands.py # /start, /help, /settings
│   │   │   ├── claude_commands.py # /claude:* commands
│   │   │   ├── collect_commands.py # /collect:* commands
│   │   │   ├── note_commands.py # /note command
│   │   │   ├── mode_commands.py # /mode, /analyze, /coach
│   │   │   └── formatting.py    # Message formatting utilities
│   │   ├── message_handlers.py   # Text/media message handling
│   │   ├── callback_handlers.py  # Inline keyboard callbacks
│   │   ├── callback_data_manager.py # Callback data serialization
│   │   ├── combined_processor.py # Routes combined buffered messages
│   │   └── keyboard_utils.py     # Inline keyboard builders (DEPRECATED)
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
│   │   ├── claude_subprocess.py   # Subprocess isolation for Claude
│   │   ├── design_skills_service.py # Design skills for UI/UX (NEW)
│   │   ├── message_buffer.py      # Message buffering for multi-part prompts
│   │   ├── reply_context.py       # Reply context tracking (enhanced)
│   │   ├── collect_service.py     # Batch collection service
│   │   ├── keyboard_service.py    # Dynamic keyboard generation
│   │   ├── voice_service.py       # Voice transcription via Groq
│   │   ├── transcript_corrector.py # LLM-based transcript correction
│   │   ├── vault_user_service.py  # Obsidian vault operations
│   │   ├── link_service.py        # Wikilink and URL handling
│   │   ├── llm_service.py         # LiteLLM integration
│   │   ├── embedding_service.py   # Text embeddings
│   │   ├── image_service.py       # Image processing
│   │   ├── gallery_service.py     # Gallery generation
│   │   ├── cache_service.py       # In-memory caching
│   │   └── job_queue_service.py   # Background job processing
│   ├── utils/               # Utilities
│   │   ├── __init__.py
│   │   ├── logging.py       # Logging configuration
│   │   ├── ngrok_utils.py   # ngrok tunnel management
│   │   ├── task_tracker.py  # Background task tracking for graceful shutdown
│   │   ├── subprocess_helper.py # Safe subprocess execution
│   │   ├── completion_reactions.py # Emoji reactions for task completion
│   │   ├── session_emoji.py # Session state emoji indicators
│   │   ├── lru_cache.py     # LRU cache implementation
│   │   ├── retry.py         # Retry decorator
│   │   ├── cleanup.py       # Resource cleanup utilities
│   │   └── ip_utils.py      # IP address utilities
│   └── main.py              # FastAPI application entry point
├── config/
│   ├── modes.yaml           # Mode and preset definitions
│   ├── ngrok.yml            # ngrok tunnel configuration
│   ├── settings.yaml        # Application settings
│   └── design_skills.yaml   # Design skills configuration (NEW)
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
├── plugins/                 # User plugins (extensible)
│   ├── claude_code/         # Claude Code integration plugin
│   │   ├── plugin.yaml      # Plugin metadata
│   │   ├── plugin.py        # Plugin class
│   │   ├── services/        # Plugin services
│   │   └── handlers/        # Command handlers
│   └── pdf/                 # PDF generation plugin
│       ├── plugin.yaml      # Plugin metadata
│       └── plugin.py        # Plugin class
├── extensions/              # Native extensions
│   ├── vector0.dylib        # SQLite vector search extension
│   └── vss0.dylib           # Vector similarity search extension
├── scripts/
│   ├── start_dev.py         # Development environment startup
│   ├── setup_webhook.py     # Webhook management utility
│   ├── daily_health_review.py # Scheduled health review
│   └── proactive_tasks/     # Proactive task framework
│       ├── __init__.py
│       ├── base_task.py     # BaseTask abstract class
│       ├── task_runner.py   # CLI runner for tasks
│       ├── task_registry.yaml # Task definitions
│       └── tasks/
│           └── daily_research.py # Daily AI research task
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md      # System architecture overview
│   └── CONTRIBUTING.md      # Contribution guide
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

#### Architecture Documentation

For comprehensive architecture details, see:
- **[Architecture Overview](docs/ARCHITECTURE.md)** - System design, layer architecture, message flow
  - API Layer (FastAPI endpoints)
  - Bot Layer (handlers, message buffer)
  - Service Layer (Claude, SRS, image processing)
  - Data Layer (SQLite, vector search)
- **[Contributing Guide](docs/CONTRIBUTING.md)** - Development setup, plugin creation
- **[Plugin Development](docs/PLUGINS.md)** - Plugin system details

The bot follows a layered architecture:
```
Telegram API → FastAPI → Bot Handlers → Combined Processor → Services → Database
                     ↓                         ↓
                 Admin API              Plugin Router
```

Key architectural patterns:
- **Subprocess isolation** for external I/O (avoid async blocking)
- **Message buffering** for multi-part prompts (2.5s timeout)
- **Background task tracking** for graceful shutdown
- **Plugin lifecycle** (discovery → loading → activation → runtime)

#### Plugin System
The bot uses a modular plugin architecture for extensibility:

- **Plugin infrastructure**: `src/plugins/` - Base classes and manager
- **User plugins**: `plugins/` - Installable plugins (claude_code is reference implementation)
- **Plugin lifecycle**: Discovery → Loading → Activation → Runtime → Deactivation

**Files:**
- `src/plugins/base.py` - `BasePlugin` class with lifecycle hooks
- `src/plugins/manager.py` - `PluginManager` for discovery and loading
- `plugins/claude_code/` - Claude Code integration as reference plugin

**Adding a new plugin:**
1. Create `plugins/my_plugin/plugin.yaml` with metadata
2. Create `plugins/my_plugin/plugin.py` with class extending `BasePlugin`
3. Implement lifecycle hooks (`on_load`, `on_activate`)
4. Register handlers via `get_command_handlers()`

See `docs/CONTRIBUTING.md` for complete plugin development guide.

#### Design Skills Integration (NEW)
Claude Code is enhanced with design guidance from industry-leading resources:

- **Service**: `src/services/design_skills_service.py`
- **Configuration**: `config/design_skills.yaml`
- **Management CLI**: `scripts/manage_design_skills.py`

**Included Design Systems:**
1. **Impeccable Style** (https://impeccable.style/) - Design fluency for AI coding tools
   - Visual hierarchy principles
   - Typography best practices
   - Color theory and accessibility
   - Spacing rhythm and consistency

2. **UI Skills** (http://ui-skills.com) - Opinionated constraints for better interfaces
   - Avoid disabled buttons (use validation messages)
   - Meaningful labels (not generic "Submit")
   - Inline validation on blur
   - Loading states for async operations
   - Error recovery guidance
   - Mobile-first design
   - Touch target sizes (44x44px minimum)
   - Focus indicators for keyboard navigation

3. **Rams.ai** (https://www.rams.ai/) - Design engineer for coding agents
   - Accessibility review checklist (WCAG AA compliance)
   - Visual consistency checks
   - UI polish recommendations
   - Auto-review on completion
   - Offers to fix identified issues

**How it works:**
- Design skills are automatically applied when Claude detects UI/design-related prompts
- Enhanced system prompt includes relevant design guidance
- Skills can be enabled/disabled per project needs
- Auto-review provides actionable feedback with code examples

**CLI Commands:**
```bash
# View current configuration
python scripts/manage_design_skills.py show

# Test if skills apply to a prompt
python scripts/manage_design_skills.py test "build a login form"

# Enable/disable specific skills
python scripts/manage_design_skills.py enable impeccable_style
python scripts/manage_design_skills.py disable ui_skills

# Get design review checklist
python scripts/manage_design_skills.py review
```

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
   - **NEW**: Extracts full context from `reply_to_message` (text, captions, media type)

2. **CombinedMessageProcessor** (`src/bot/combined_processor.py`):
   - Routes combined messages based on content type
   - Handles `/claude` commands with combined prompts
   - Runs Claude execution in background tasks (avoids blocking)
   - **NEW**: Creates ReplyContext on cache misses (reply to any message)

3. **ReplyContext** (`src/services/reply_context.py`):
   - Tracks message origins for reply handling
   - Enables "reply to continue" functionality
   - 24-hour TTL LRU cache
   - **NEW**: Works for all message types (text, voice, images, videos, documents)

**Flow**:
```
User sends /claude prompt → Buffer collects
User sends more text     → Buffer adds to collection
2.5s timeout             → Buffer flushes
CombinedMessageProcessor → Routes to Claude
Background task          → Executes Claude prompt
```

**Reply Context Flow** (see [REPLY_CONTEXT_IMPLEMENTATION.md](REPLY_CONTEXT_IMPLEMENTATION.md)):
```
User replies to message  → Extract reply_to_message content
Check cache              → If miss, create context from extracted content
Build prompt             → Include original message + response
Send to Claude           → Full context preserved
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
- Supports multiple modes: default, formal (with structured YAML output)

#### Settings System (NEW)
- User preferences stored in `chats` table
- **Model selection**: Choose default Claude model (haiku/sonnet/opus)
- **Model buttons toggle**: Show/hide model buttons in keyboards
- Accessed via `/settings` command
- See [docs/MODEL_SETTINGS.md](docs/MODEL_SETTINGS.md) for details

#### Voice & Video Transcription (NEW)
- **Voice Service** (`src/services/voice_service.py`): Transcription via Groq Whisper
- **Transcript Correction** (`src/services/transcript_corrector.py`): LLM-based correction with configurable levels
- Auto-forward to Claude in locked mode
- Configurable correction levels: off, light, moderate, aggressive
- See recent commit: `feat: add transcript correction with configurable levels`

#### Collect Mode (Batch Processing) (NEW)
- **Service**: `src/services/collect_service.py`
- **Commands**: `/collect:start`, `/collect:go`, `/collect:stop`, `/collect:status`, `/collect:clear`
- Accumulate multiple items (text, images, voice, videos) before processing
- Process everything together with Claude for comprehensive analysis
- Queue management with status display

#### Obsidian Vault Integration (NEW)
- **Service**: `src/services/vault_user_service.py`
- **Link Service**: `src/services/link_service.py` - Wikilink parsing and deep links
- **Commands**: `/note <name>` - View vault notes in Telegram
- Clickable `[[wikilinks]]` with deep link navigation (`obsidian://open?vault=...`)
- Read, search, and edit notes through Claude sessions
- **Auto-linking**: Claude Code automatically converts full vault paths (e.g., `/Users/server/Research/vault/Note.md`) in responses to clickable Obsidian links

#### Keyboard Management (NEW)
- **Keyboard Service** (`src/services/keyboard_service.py`): Dynamic keyboard generation
- **Callback Data Manager** (`src/bot/callback_data_manager.py`): Serialize complex callback data
- Database-backed keyboard configurations (`keyboard_config` table)
- Support for dynamic buttons, toggles, and model selection

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

# Groq (for voice transcription)
GROQ_API_KEY=your_groq_key

# ngrok Configuration
NGROK_AUTHTOKEN=your_ngrok_authtoken_here
NGROK_AUTO_UPDATE=true
NGROK_PORT=8847  # Production port
NGROK_REGION=us
NGROK_TUNNEL_NAME=telegram-agent

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/telegram_agent.db

# Obsidian Vault
OBSIDIAN_VAULT_PATH=/Users/server/Research/vault
OBSIDIAN_VAULT_NAME=vault

# Application
DEBUG=false
LOG_LEVEL=INFO
PYTHON_EXECUTABLE=/opt/homebrew/bin/python3.11
```

### Database Operations
- **Models**: SQLAlchemy ORM models in `src/models/`
- **Migrations**: Use Alembic for schema changes
- **Vector Search**: sqlite-vss for similarity search (extensions in `extensions/`)
- **New tables**:
  - `collect_sessions` - Batch collection state
  - `keyboard_config` - Dynamic keyboard configurations
  - `messages` - Message history
  - `routing_memory` - Routing decisions cache

### Testing Strategy
- **Unit Tests**: Mock external APIs (Telegram, OpenAI, Groq)
- **Integration Tests**: Test complete workflows with test fixtures
- **Service Tests**: Comprehensive coverage for core services (SRS, design skills, Claude)
- **Test Images**: Store in `tests/fixtures/`
- **Coverage**: Currently >75% code coverage, targeting >80%

**Recent test additions:**
- SRS algorithm tests (SM-2 implementation)
- Design skills service tests (17/17 passing)
- Claude subprocess tests (isolation verification)
- Reply context tests (all message types)
- Session naming tests (AI generation)

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

#### Obsidian Note References in Claude Responses
When Claude Code mentions vault notes, always use full absolute paths. The bot automatically converts these to clickable Obsidian deep links:

```python
# In Claude Code responses:
# GOOD - Full path (becomes clickable link):
"Created note: /Users/server/Research/vault/Research/Notes/Mem0.md"

# BAD - Relative path (won't be linkified):
"Created note: Research/Notes/Mem0.md"

# GOOD - Multiple references:
"Updated files: /Users/server/Research/vault/Config.md, /Users/server/Research/vault/Index.md"
```

The system prompt in `claude_code_service.py` instructs Claude to use this format automatically.

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

#### Recent Features & Changes (Last Month)

1. **SRS (Spaced Repetition System)** (Jan 18): Complete SM-2 algorithm implementation with vault sync
2. **Design Skills Integration** (Jan 17): Automatic UI/UX guidance from 3 design systems
3. **Session Auto-naming** (Jan 15): AI-generated concise session names with rename/delete
4. **Daily Research Task** (Jan 14): Proactive AI research summaries sent to Obsidian
5. **Transcript Correction** (Jan 11): LLM-based correction with configurable levels
6. **Auto-forward Voice to Claude** (Jan 11): New session trigger in locked mode
7. **Enhanced Reply Context** (Jan 18): Extract full context from `reply_to_message` for all types
8. **Vault Path Wikilinks** (Jan 16): Full paths auto-convert to clickable Obsidian links
9. **Launchd Service** (Jan 8): System service configuration for reliability
10. **Modular Handler Architecture** (Jan 1): Split handlers into focused modules

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

##### Design Skills Limitations
- **Keyword detection only**: Requires UI/design keywords in prompt to activate
- **Static guidance**: Cannot adapt to project-specific design systems
- **No visual verification**: Cannot validate actual visual output

##### SRS Limitations
- **Local database only**: Not distributed across devices
- **Manual vault path config**: Requires absolute path configuration
- **No mobile app**: Telegram-only interface

### Async/Subprocess Architecture Pattern

> **CRITICAL FOR CONTRIBUTORS**: This section explains a fundamental architectural pattern that affects all external I/O in this codebase.

#### The Problem
The bot runs inside uvicorn's event loop with python-telegram-bot. This creates a nested async context where certain operations **block indefinitely** even though they work fine in standalone `asyncio.run()`.

#### Why This Happens
```
uvicorn event loop
  └── FastAPI lifespan
       └── python-telegram-bot Application
            └── Webhook handler context
                 └── Your async code ← BLOCKING CONTEXT
```

When code runs in the webhook handler context, some async operations wait forever because they're trying to use the same event loop that's waiting for them to complete.

#### Operations That Block
| Operation | Why It Blocks |
|-----------|---------------|
| `context.bot.get_file()` | Telegram SDK async in nested context |
| `context.bot.send_message()` | Same as above |
| `message.edit_text()` | Same as above |
| Claude Code SDK `query()` | httpx async client in nested context |
| `httpx.AsyncClient` requests | Event loop contention |
| Groq/OpenAI API calls | httpx-based, same issue |

#### The Solution: Subprocess Isolation
Execute blocking operations in a subprocess to get a fresh event loop:

```python
import subprocess
from src.core.config import get_settings

def send_message_sync(chat_id: int, text: str, token: str) -> bool:
    """Send message via subprocess to avoid async blocking."""
    script = f'''
import requests
response = requests.post(
    "https://api.telegram.org/bot{token}/sendMessage",
    json={{"chat_id": {chat_id}, "text": """{text}"""}}
)
print("OK" if response.ok else "FAIL")
'''
    python_path = get_settings().python_executable
    result = subprocess.run(
        [python_path, "-c", script],
        capture_output=True,
        text=True,
        timeout=30
    )
    return "OK" in result.stdout
```

#### Helper Functions Available
| Function | Location | Purpose |
|----------|----------|---------|
| `send_message_sync()` | `src/bot/handlers.py` | Send Telegram messages |
| `edit_message_sync()` | `src/bot/handlers.py` | Edit Telegram messages |
| `download_file_sync()` | `src/bot/combined_processor.py` | Download Telegram files |
| `run_claude_subprocess()` | `src/services/claude_subprocess.py` | Execute Claude queries |
| `transcribe_audio_sync()` | `src/bot/combined_processor.py` | Transcribe audio via Groq |

#### When to Use Subprocess vs Background Task

**Use subprocess** for:
- Telegram API calls (send/edit messages, download files)
- Claude Code SDK queries
- External API calls (Groq, OpenAI direct)

**Use background task** for:
- Long-running operations that call subprocesses internally
- Operations that need to send multiple messages

```python
from src.utils.task_tracker import create_tracked_task

# Long-running Claude conversation
async def run_claude_conversation():
    # This internally uses subprocess for each Claude call
    result = run_claude_subprocess(prompt)
    send_message_sync(chat_id, result, token)

# Launch as tracked background task
create_tracked_task(run_claude_conversation(), name="claude_chat")
```

#### Trade-offs
- **Overhead**: ~100ms per subprocess call
- **Memory**: Each subprocess spawns a new Python interpreter
- **Suitability**: Fine for personal/small-group bots, not for high-throughput

For high-throughput scenarios, consider:
- Moving to polling mode instead of webhooks
- Using a separate worker process with message queue
- Celery or similar task queue

### Git Workflow
- **Branch naming**: feature/description or fix/description
- **Commit messages**: Use conventional commits format
- **Before committing**: Run linting, type checking, and tests
- **Pull requests**: Include test coverage and documentation updates

Remember: Always run linting and fix errors before building!