# Architecture Overview

This document describes the architecture of the Telegram Agent bot, a modular Telegram bot with AI capabilities, image processing, and a plugin system.

## Table of Contents

- [System Overview](#system-overview)
- [Layer Architecture](#layer-architecture)
- [Message Flow](#message-flow)
- [Key Components](#key-components)
- [Plugin System](#plugin-system)
- [Database Design](#database-design)
- [Async Patterns](#async-patterns)
- [Configuration](#configuration)
- [Known Limitations](#known-limitations)

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram API                              │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Webhook
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Application                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  /webhook    │  │  /api/*      │  │  /health     │          │
│  │  endpoint    │  │  admin API   │  │  monitoring  │          │
│  └──────┬───────┘  └──────────────┘  └──────────────┘          │
└─────────┼───────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Bot Layer                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Handlers   │  │   Message    │  │   Callback   │          │
│  │  /commands   │  │   Buffer     │  │   Handlers   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘          │
└─────────┼─────────────────┼─────────────────────────────────────┘
          │                 │
          ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Combined Processor                             │
│         Routes messages to appropriate handlers                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐               │
│  │ Plugin  │ │ Claude  │ │ Collect │ │ Image   │               │
│  │ Router  │ │  Mode   │ │  Mode   │ │ Process │               │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘               │
└───────┼───────────┼───────────┼───────────┼─────────────────────┘
        │           │           │           │
        ▼           ▼           ▼           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Service Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Claude Code  │  │   Collect    │  │    Image     │          │
│  │   Service    │  │   Service    │  │   Service    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  LLM Service │  │   Vector     │  │  Embedding   │          │
│  │  (LiteLLM)   │  │   Service    │  │   Service    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Data Layer                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   SQLite     │  │    Files     │  │   Vector     │          │
│  │  (async)     │  │  (raw/img)   │  │   Store      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer Architecture

### 1. API Layer (`src/api/`)

FastAPI endpoints for external communication:

| Endpoint | Purpose |
|----------|---------|
| `/webhook` | Telegram webhook receiver |
| `/api/health` | Health checks and monitoring |
| `/api/messaging` | Authenticated messaging API |
| `/api/webhook/*` | Webhook management |

### 2. Bot Layer (`src/bot/`)

Telegram bot command and message handling:

| File | Responsibility |
|------|----------------|
| `bot.py` | Bot initialization, application setup |
| `handlers.py` | Command handlers (`/start`, `/claude`, etc.) |
| `message_handlers.py` | Text and media message handling |
| `callback_handlers.py` | Inline keyboard callbacks |
| `combined_processor.py` | Message routing and processing |
| `keyboard_utils.py` | Inline keyboard builders |

### 3. Service Layer (`src/services/`)

Business logic and external integrations:

| Service | Purpose |
|---------|---------|
| `claude_code_service.py` | Claude Code SDK integration |
| `claude_subprocess.py` | Subprocess wrapper for Claude |
| `message_buffer.py` | Multi-part message batching |
| `collect_service.py` | Image collection mode |
| `llm_service.py` | LiteLLM integration |
| `embedding_service.py` | Text embeddings |
| `vector_service.py` | Similarity search |
| `image_service.py` | Image processing |

### 4. Core Layer (`src/core/`)

Foundational components:

| File | Purpose |
|------|---------|
| `database.py` | Async SQLAlchemy setup |
| `config.py` | Pydantic settings |
| `services.py` | Service container (DI) |
| `mode_manager.py` | Bot mode switching |

### 5. Plugin Layer (`src/plugins/`, `plugins/`)

Extensibility framework:

| File | Purpose |
|------|---------|
| `base.py` | Plugin base class and lifecycle |
| `manager.py` | Plugin discovery and loading |
| `models.py` | Plugin database model support |

---

## Message Flow

### 1. Webhook Reception

```
Telegram → POST /webhook → validate_secret → process_update
```

### 2. Message Buffering

Messages are buffered for 2.5 seconds to combine multi-part inputs:

```python
# User sends:
#   Message 1: "/claude"
#   Message 2: "analyze this"
#   Message 3: [image]
#
# Buffer combines into single CombinedMessage:
#   - text: "/claude analyze this"
#   - images: [image_data]
```

### 3. Message Routing

```python
CombinedProcessor.process(combined_message):
    1. Check plugin handlers
    2. Check /claude command
    3. Check collect mode
    4. Check Claude mode (locked)
    5. Route to content-specific handler
```

### 4. Response Delivery

Responses are sent via subprocess to avoid async blocking (see [Async Patterns](#async-patterns)).

---

## Key Components

### Message Buffer (`src/services/message_buffer.py`)

Combines rapid-fire messages into single processing units:

```
User messages (within 2.5s)  →  Buffer  →  CombinedMessage
     /claude                      │
     please analyze               │
     [image.jpg]                  │
                                  ▼
                         Single processing call
```

**Key features:**
- Per-(chat_id, user_id) buffering
- 2.5 second flush timeout
- Supports text, images, voice, documents
- Special handling for `/claude` commands

### Combined Processor (`src/bot/combined_processor.py`)

Central message routing hub:

```python
class CombinedMessageProcessor:
    async def process(self, combined: CombinedMessage):
        # 1. Plugin routing
        if await plugin_manager.route_message(combined):
            return

        # 2. Claude command handling
        if combined.has_claude_command():
            await self._process_claude_command(combined)
            return

        # 3. Mode-specific routing
        if await self._check_collect_mode(combined):
            return

        if await self._check_claude_mode(combined):
            return

        # 4. Content-type routing
        await self._route_by_content(combined)
```

### Service Container (`src/core/services.py`)

Dependency injection for services:

```python
container = ServiceContainer()
container.register("claude_service", ClaudeCodeService())
container.register("image_service", ImageService())

# Usage
claude = container.get("claude_service")
```

---

## Plugin System

### Plugin Structure

```
plugins/
└── my_plugin/
    ├── plugin.yaml      # Metadata and config
    ├── plugin.py        # Main plugin class
    ├── handlers/        # Command handlers
    ├── services/        # Plugin services
    └── models/          # Database models
```

### Plugin Lifecycle

```
1. Discovery   →  Find plugin.yaml files
2. Loading     →  Import plugin class, register services
3. Activation  →  Register handlers with bot
4. Runtime     →  Handle messages, callbacks
5. Deactivation →  Cleanup before disable
6. Unloading   →  Final cleanup
```

### Creating a Plugin

```python
# plugins/my_plugin/plugin.py
from src.plugins.base import BasePlugin, PluginMetadata

class MyPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
        )

    async def on_load(self, container) -> bool:
        # Register services
        return True

    async def on_activate(self, app) -> bool:
        # Register handlers
        return True
```

See `plugins/claude_code/` for a complete example.

---

## Database Design

### Models (`src/models/`)

| Model | Purpose |
|-------|---------|
| `User` | Telegram user data |
| `Chat` | Chat settings, modes |
| `Image` | Processed images with embeddings |
| `ClaudeSession` | Claude conversation sessions |
| `AdminContact` | Authorized admin users |

### Session Management

```python
from src.core.database import get_db_session

async with get_db_session() as session:
    user = await session.get(User, user_id)
    user.last_active = datetime.now()
    await session.commit()
```

### SQLite Considerations

The bot uses SQLite with async support (`aiosqlite`). Key considerations:

1. **Single-writer limitation**: Only one write transaction at a time
2. **In-memory caches**: Used to avoid deadlocks during message buffer processing
3. **No migrations**: Schema changes require manual handling

---

## Async Patterns

### The Subprocess Pattern

Due to event loop conflicts between FastAPI/uvicorn and python-telegram-bot, certain operations are executed in subprocesses:

```python
# Operations that block in bot context:
# - context.bot.get_file()
# - context.bot.send_message()
# - Claude Code SDK queries
# - httpx.AsyncClient requests

# Solution: Execute in subprocess
def send_message_sync(chat_id, text):
    script = '''
    import requests
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", ...)
    '''
    subprocess.run([python_path, "-c", script], ...)
```

**Why this pattern?**
- The bot runs inside uvicorn's event loop
- python-telegram-bot has its own async context
- Certain async operations block indefinitely
- Subprocess isolates the blocking call

**Trade-off:**
- ~100ms overhead per subprocess call
- Suitable for personal/small-group bots
- Not ideal for high-throughput scenarios

### Background Task Tracking

Long-running tasks are tracked for graceful shutdown:

```python
from src.utils.task_tracker import create_tracked_task

# Bad - orphaned on shutdown
asyncio.create_task(long_running_operation())

# Good - tracked and cancelled gracefully
create_tracked_task(long_running_operation(), name="my_task")
```

---

## Configuration

### Environment Variables

Primary configuration via `.env`:

```bash
# Required
TELEGRAM_BOT_TOKEN=your_token
DATABASE_URL=sqlite+aiosqlite:///./data/telegram_agent.db

# Optional
OPENAI_API_KEY=for_llm_features
ANTHROPIC_API_KEY=for_claude_features
```

### Configuration Files

| File | Purpose |
|------|---------|
| `config/modes.yaml` | Bot modes and presets |
| `config/defaults.yaml` | Default values |
| `config/settings.yaml` | Application settings |

### Settings Access

```python
from src.core.config import get_settings

settings = get_settings()
token = settings.telegram_bot_token
```

---

## Known Limitations

### 1. Single-Server Architecture

- SQLite limits to single-writer
- In-memory caches not distributed
- Not horizontally scalable

### 2. Subprocess Overhead

- ~100ms per Telegram API call
- Not suitable for >100 messages/second
- Higher memory usage due to subprocess spawning

### 3. Message Buffer Delay

- Fixed 2.5 second buffer timeout
- Single messages feel slightly delayed
- Trade-off for multi-part message support

### 4. No Database Migrations

- Schema changes require manual SQL
- No version tracking for database schema
- Alembic installed but not configured

---

## Directory Structure

```
telegram_agent/
├── src/
│   ├── api/              # FastAPI endpoints
│   ├── bot/              # Telegram bot handlers
│   ├── core/             # Database, config, DI
│   ├── middleware/       # Error handling
│   ├── models/           # SQLAlchemy models
│   ├── plugins/          # Plugin infrastructure
│   ├── services/         # Business logic
│   ├── utils/            # Utilities
│   └── main.py           # Application entry
├── plugins/              # User plugins
├── config/               # Configuration files
├── data/                 # SQLite database, files
├── logs/                 # Application logs
├── tests/                # Test suite
├── scripts/              # Utility scripts
└── docs/                 # Documentation
```

---

## Further Reading

- [CONTRIBUTING.md](CONTRIBUTING.md) - How to contribute
- [CLAUDE.md](../CLAUDE.md) - Development instructions
- [Plugin Development](PLUGIN_DEVELOPMENT.md) - Creating plugins
