# Contributing Guide

Thank you for your interest in contributing to Verity! This guide will help you get started.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Creating Plugins](#creating-plugins)

---

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- ngrok (for local webhook testing)
- A Telegram Bot Token (from [@BotFather](https://t.me/botfather))

### Quick Start

```bash
# Clone the repository
git clone https://github.com/glebis/verity-agent.git
cd verity-agent

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your bot token

# Run the bot
python -m uvicorn src.main:app --reload --port 8000
```

---

## Development Setup

### Environment Variables

Create a `.env` file with at minimum:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
DATABASE_URL=sqlite+aiosqlite:///./data/telegram_agent.db
ENVIRONMENT=development
```

### Running with Webhook (Local Development)

```bash
# Terminal 1: Start ngrok
ngrok http 8000

# Terminal 2: Start the bot
python scripts/start_dev.py start --port 8000
```

The bot will automatically detect ngrok and configure the webhook.

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html

# Run specific test file
python -m pytest tests/test_plugins/test_plugin_manager.py -v
```

---

## Code Style

### Formatting

We use Black, isort, and flake8:

```bash
# Format code
python -m black src/ tests/
python -m isort src/ tests/

# Check linting
python -m flake8 src/ tests/

# Type checking
python -m mypy src/
```

### Style Guidelines

1. **Type hints**: Use type hints for all function signatures
2. **Docstrings**: Google-style docstrings for public functions
3. **Line length**: 88 characters (Black default)
4. **Imports**: Grouped (stdlib, third-party, local)

```python
# Good example
from typing import Optional, List

from telegram import Update
from telegram.ext import ContextTypes

from src.core.database import get_db_session
from src.models.user import User


async def get_user(user_id: int) -> Optional[User]:
    """
    Retrieve a user by their Telegram ID.

    Args:
        user_id: The Telegram user ID.

    Returns:
        The User object if found, None otherwise.
    """
    async with get_db_session() as session:
        return await session.get(User, user_id)
```

---

## Making Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring

### Commit Messages

Use conventional commits:

```
feat: add user preferences command
fix: resolve message buffer timeout issue
docs: update plugin development guide
refactor: split handlers into modules
test: add combined processor tests
```

### Architecture Guidelines

Before making changes, understand the layer architecture:

```
API Layer (src/api/)
    ↓
Bot Layer (src/bot/)
    ↓
Service Layer (src/services/)
    ↓
Data Layer (src/core/, src/models/)
```

**Key principles:**

1. **Services don't import from bot layer** - Keep service layer independent
2. **Use dependency injection** - Register services in container
3. **Avoid circular imports** - Use lazy imports if necessary
4. **Document workarounds** - Explain any async/subprocess patterns

### Adding a New Command

1. Add handler in `src/bot/handlers.py`:

```python
async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mycommand."""
    user = update.effective_user
    chat = update.effective_chat

    # Your logic here
    await update.message.reply_text("Response")
```

2. Register in `src/bot/bot.py`:

```python
from .handlers import my_command

# In _setup_application():
application.add_handler(CommandHandler("mycommand", my_command))
```

### Adding a New Service

1. Create service file in `src/services/`:

```python
# src/services/my_service.py
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class MyService:
    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service."""
        self._initialized = True
        logger.info("MyService initialized")

    async def do_something(self, param: str) -> Optional[str]:
        """Perform an operation."""
        if not self._initialized:
            raise RuntimeError("Service not initialized")
        return f"Result: {param}"


# Singleton accessor
_instance: Optional[MyService] = None

def get_my_service() -> MyService:
    global _instance
    if _instance is None:
        _instance = MyService()
    return _instance
```

2. Register in `src/core/services.py` if using DI container.

---

## Testing

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── test_bot/             # Bot layer tests
├── test_core/            # Core layer tests
├── test_services/        # Service layer tests
├── test_plugins/         # Plugin system tests
└── test_utils/           # Utility tests
```

### Writing Tests

```python
# tests/test_services/test_my_service.py
import pytest
from src.services.my_service import MyService


class TestMyService:
    @pytest.fixture
    def service(self):
        return MyService()

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        """Test service initialization."""
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_do_something(self, service):
        """Test do_something method."""
        await service.initialize()
        result = await service.do_something("test")
        assert result == "Result: test"

    @pytest.mark.asyncio
    async def test_do_something_not_initialized(self, service):
        """Test error when not initialized."""
        with pytest.raises(RuntimeError):
            await service.do_something("test")
```

### Mocking External Services

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock():
    with patch("src.services.llm_service.LLMService.query") as mock_query:
        mock_query.return_value = "Mocked response"
        # Test code that uses LLM service
```

---

## Submitting Changes

### Pull Request Process

1. **Fork** the repository
2. **Create** a feature branch
3. **Make** your changes
4. **Run** tests and linting
5. **Push** to your fork
6. **Open** a pull request

### PR Checklist

- [ ] Tests pass (`pytest tests/`)
- [ ] Linting passes (`flake8`, `black --check`, `isort --check`)
- [ ] Type checking passes (`mypy src/`)
- [ ] Documentation updated if needed
- [ ] Commit messages follow convention

### PR Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactoring

## Testing
How was this tested?

## Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes
```

---

## Creating Plugins

Plugins are the preferred way to add new features.

### Plugin Structure

```
plugins/
└── my_plugin/
    ├── plugin.yaml       # Required: metadata
    ├── plugin.py         # Required: plugin class
    ├── __init__.py
    ├── handlers/         # Optional: command handlers
    │   └── __init__.py
    ├── services/         # Optional: plugin services
    │   └── __init__.py
    └── models/           # Optional: database models
        └── __init__.py
```

### plugin.yaml

```yaml
name: my-plugin
version: "1.0.0"
description: "Description of my plugin"
author: "Your Name"
enabled: true
priority: 100

# Required environment variables
requires:
  - MY_API_KEY

# Other plugins this depends on
dependencies: []

# Plugin-specific configuration
config:
  setting1: value1
  setting2: value2
```

### plugin.py

```python
from typing import List, Optional
from telegram.ext import BaseHandler, CommandHandler

from src.plugins.base import (
    BasePlugin,
    PluginCapabilities,
    PluginMetadata,
)


class MyPlugin(BasePlugin):
    """My custom plugin."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="Description of my plugin",
            author="Your Name",
            requires=["MY_API_KEY"],
            dependencies=[],
            priority=100,
        )

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            commands=["mycommand"],
            message_handler=False,
        )

    async def on_load(self, container) -> bool:
        """Called when plugin is loaded."""
        self.logger.info("Loading my plugin...")
        # Register services, load config
        return True

    async def on_activate(self, app) -> bool:
        """Called when bot is ready."""
        self.logger.info("Activating my plugin...")
        # Handlers are registered automatically
        return True

    def get_command_handlers(self) -> List[BaseHandler]:
        """Return command handlers."""
        return [
            CommandHandler("mycommand", self._handle_mycommand),
        ]

    async def _handle_mycommand(self, update, context):
        """Handle /mycommand."""
        await update.message.reply_text("Hello from my plugin!")
```

### Testing Your Plugin

```bash
# Enable the plugin (already enabled by default if enabled: true in yaml)

# Restart the bot
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist

# Check logs for plugin loading
tail -f logs/app.log | grep -i plugin
```

---

## Questions?

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Join discussions for architectural decisions

Thank you for contributing!
