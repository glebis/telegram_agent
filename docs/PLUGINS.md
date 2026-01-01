# Plugin Development Guide

This guide covers everything you need to create plugins for Telegram Agent.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Plugin Structure](#plugin-structure)
- [Plugin Lifecycle](#plugin-lifecycle)
- [Plugin Capabilities](#plugin-capabilities)
- [Examples](#examples)
- [Best Practices](#best-practices)
- [Debugging](#debugging)

---

## Overview

Plugins are the preferred way to extend Telegram Agent. They provide:

- **Isolation**: Self-contained modules with their own services, handlers, and models
- **Lifecycle Management**: Load, activate, deactivate, unload hooks
- **Priority Routing**: Control message processing order
- **Hot Configuration**: Enable/disable via YAML without code changes

### Plugin Locations

| Location | Purpose |
|----------|---------|
| `plugins/` | User plugins (your custom plugins go here) |
| `src/plugins/builtin/` | Built-in plugins (shipped with bot) |

---

## Quick Start

### 1. Create Plugin Directory

```bash
mkdir -p plugins/my_plugin
```

### 2. Create plugin.yaml

```yaml
# plugins/my_plugin/plugin.yaml
name: my-plugin
version: "1.0.0"
description: "My awesome plugin"
author: "Your Name"
enabled: true
priority: 100  # Lower = higher priority

requires: []      # Required env vars
dependencies: []  # Required plugins

config:
  greeting: "Hello from my plugin!"
```

### 3. Create plugin.py

```python
# plugins/my_plugin/plugin.py
from typing import List
from telegram.ext import BaseHandler, CommandHandler

from src.plugins.base import BasePlugin, PluginCapabilities, PluginMetadata


class MyPlugin(BasePlugin):
    """My custom plugin."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My awesome plugin",
            author="Your Name",
        )

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            commands=["hello"],
            message_handler=False,
        )

    async def on_load(self, container) -> bool:
        """Called when plugin loads. Register services here."""
        self.greeting = self.config.get("greeting", "Hello!")
        self.logger.info(f"Loaded with greeting: {self.greeting}")
        return True

    async def on_activate(self, app) -> bool:
        """Called when bot is ready. Handlers auto-registered."""
        return True

    def get_command_handlers(self) -> List[BaseHandler]:
        """Return command handlers to register."""
        return [
            CommandHandler("hello", self._handle_hello),
        ]

    async def _handle_hello(self, update, context):
        """Handle /hello command."""
        await update.message.reply_text(self.greeting)
```

### 4. Restart Bot

```bash
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist && \
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist
```

### 5. Test

Send `/hello` to your bot.

---

## Plugin Structure

### Minimal Structure

```
plugins/my_plugin/
├── plugin.yaml    # Required: metadata
└── plugin.py      # Required: plugin class
```

### Full Structure

```
plugins/my_plugin/
├── plugin.yaml         # Metadata and config
├── plugin.py           # Main plugin class
├── __init__.py
├── handlers/           # Command handlers
│   ├── __init__.py
│   └── commands.py
├── services/           # Plugin services
│   ├── __init__.py
│   └── my_service.py
└── models/             # Database models
    ├── __init__.py
    └── my_model.py
```

### plugin.yaml Reference

```yaml
# Identity
name: my-plugin              # Unique identifier (kebab-case)
version: "1.0.0"             # Semantic version
description: "What it does"  # Short description
author: "Your Name"          # Author name

# Lifecycle
enabled: true                # Can be disabled without removing
priority: 100                # Message routing priority (lower = higher)

# Dependencies
requires:                    # Required environment variables
  - MY_API_KEY
  - MY_SECRET
dependencies:                # Required plugins (loaded first)
  - other-plugin

# Custom configuration (accessible via self.config)
config:
  setting1: value1
  setting2: value2
  nested:
    key: value
```

---

## Plugin Lifecycle

```
┌─────────────┐
│  Discovery  │  Find plugin.yaml files
└──────┬──────┘
       ▼
┌─────────────┐
│   Loading   │  on_load() - Register services, validate config
└──────┬──────┘
       ▼
┌─────────────┐
│ Activation  │  on_activate() - Register handlers (bot ready)
└──────┬──────┘
       ▼
┌─────────────┐
│   Runtime   │  Process messages, handle callbacks
└──────┬──────┘
       ▼
┌─────────────┐
│Deactivation │  on_deactivate() - Cleanup before disable
└──────┬──────┘
       ▼
┌─────────────┐
│  Unloading  │  on_unload() - Final cleanup on shutdown
└─────────────┘
```

### Lifecycle Hooks

| Hook | When | Use For |
|------|------|---------|
| `on_load(container)` | Plugin discovered | Service registration, config validation |
| `on_activate(app)` | Bot initialized | Handler registration (auto), runtime setup |
| `on_deactivate()` | Plugin disabling | Cleanup active resources |
| `on_unload()` | Bot shutdown | Final cleanup |

---

## Plugin Capabilities

### Commands

Register Telegram command handlers:

```python
def get_command_handlers(self) -> List[BaseHandler]:
    return [
        CommandHandler("cmd1", self._handle_cmd1),
        CommandHandler("cmd2", self._handle_cmd2),
        MessageHandler(filters.PHOTO, self._handle_photo),
    ]
```

### Callbacks

Handle inline keyboard button presses:

```python
def get_callback_prefix(self) -> str:
    return "myplugin"  # Handles callbacks starting with "myplugin:"

async def handle_callback(self, update, context, action: str, data: str):
    # action = part after prefix (e.g., "myplugin:action" -> "action")
    # data = any additional data
    if action == "confirm":
        await update.callback_query.answer("Confirmed!")
```

### Message Processor

Intercept messages before default routing:

```python
@property
def capabilities(self) -> PluginCapabilities:
    return PluginCapabilities(
        commands=["mycmd"],
        message_handler=True,  # Enable message processing
    )

def get_message_processor(self):
    return self._process_message

async def _process_message(self, combined) -> bool:
    """Process message. Return True if handled, False to continue."""
    if "keyword" in combined.text.lower():
        # Handle it
        return True
    return False  # Let other handlers process
```

### API Routes

Add FastAPI endpoints:

```python
from fastapi import APIRouter

def get_api_router(self) -> APIRouter:
    router = APIRouter(prefix="/myplugin", tags=["myplugin"])

    @router.get("/status")
    async def get_status():
        return {"status": "ok"}

    return router
```

### Database Models

Register SQLAlchemy models:

```python
from sqlalchemy import Column, Integer, String
from src.core.database import Base

class MyModel(Base):
    __tablename__ = "myplugin_items"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))

def get_database_models(self):
    return [MyModel]
```

### Service Registration

Register services in the DI container:

```python
async def on_load(self, container) -> bool:
    from .services.my_service import MyService

    container.register_singleton(
        "my_service",
        lambda: MyService(self.config)
    )
    return True
```

---

## Examples

### Example 1: Simple Command Plugin

```python
class GreetPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(name="greet", version="1.0.0")

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(commands=["greet"])

    def get_command_handlers(self):
        return [CommandHandler("greet", self._greet)]

    async def _greet(self, update, context):
        name = update.effective_user.first_name
        await update.message.reply_text(f"Hello, {name}!")
```

### Example 2: Callback Plugin with Inline Keyboard

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class VotePlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(name="vote", version="1.0.0")

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(commands=["vote"], callbacks=True)

    def get_command_handlers(self):
        return [CommandHandler("vote", self._start_vote)]

    def get_callback_prefix(self) -> str:
        return "vote"

    async def _start_vote(self, update, context):
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Yes", callback_data="vote:yes"),
                InlineKeyboardButton("No", callback_data="vote:no"),
            ]
        ])
        await update.message.reply_text("Do you agree?", reply_markup=keyboard)

    async def handle_callback(self, update, context, action, data):
        await update.callback_query.answer(f"You voted: {action}")
        await update.callback_query.edit_message_text(f"Vote recorded: {action}")
```

### Example 3: Message Interceptor Plugin

```python
class AutoReplyPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(name="autoreply", version="1.0.0", priority=10)

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(message_handler=True)

    def get_message_processor(self):
        return self._check_keywords

    async def _check_keywords(self, combined) -> bool:
        keywords = {"help": "How can I help you?", "thanks": "You're welcome!"}

        for keyword, response in keywords.items():
            if keyword in combined.text.lower():
                # Use subprocess helper for Telegram API
                from src.bot.handlers import send_message_sync
                send_message_sync(
                    combined.chat_id,
                    response,
                    combined.context.bot.token
                )
                return True
        return False
```

---

## Best Practices

### 1. Use Subprocess for Telegram API

Due to event loop conflicts, use subprocess helpers:

```python
# BAD - blocks in webhook context
await context.bot.send_message(chat_id, text)

# GOOD - uses subprocess
from src.bot.handlers import send_message_sync
send_message_sync(chat_id, text, context.bot.token)
```

### 2. Handle Errors Gracefully

```python
async def on_load(self, container) -> bool:
    try:
        # Initialization
        return True
    except Exception as e:
        self.logger.error(f"Failed to load: {e}")
        return False  # Plugin won't activate
```

### 3. Clean Up Resources

```python
async def on_deactivate(self):
    if hasattr(self, '_client'):
        await self._client.close()

async def on_unload(self):
    # Final cleanup
    pass
```

### 4. Use Plugin Config

```yaml
# plugin.yaml
config:
  api_url: "https://api.example.com"
  timeout: 30
```

```python
async def on_load(self, container) -> bool:
    self.api_url = self.config.get("api_url")
    self.timeout = self.config.get("timeout", 30)
    return True
```

### 5. Log Everything

```python
async def _handle_command(self, update, context):
    self.logger.info(
        "Command received",
        extra={
            "user_id": update.effective_user.id,
            "chat_id": update.effective_chat.id,
        }
    )
```

---

## Debugging

### Check Plugin Loading

```bash
# View plugin loading logs
tail -f logs/app.log | grep -i plugin

# Expected output:
# Loading Claude Code plugin...
# Loaded plugin: claude-code v1.0.0
# Activated plugin: claude-code
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Plugin not loading | Missing `plugin.yaml` | Create metadata file |
| Plugin not activating | `on_load()` returned False | Check logs for errors |
| Commands not working | Missing `get_command_handlers()` | Implement method |
| Import errors | Circular imports | Use lazy imports |

### Test Plugin in Isolation

```python
# test_my_plugin.py
import pytest
from plugins.my_plugin.plugin import MyPlugin

@pytest.mark.asyncio
async def test_plugin_load():
    plugin = MyPlugin()
    result = await plugin.on_load(mock_container)
    assert result is True
```

---

## Reference Implementation

See `plugins/claude_code/` for a complete example with:
- Service registration
- Command handlers
- Callback handling
- Message processing
- Database model integration
- Background task execution

---

## Plugin Ideas

Looking for inspiration? Here are some useful plugins to build:

| Plugin | Description |
|--------|-------------|
| **reminder** | Schedule messages and reminders |
| **translate** | Auto-translate messages |
| **summarize** | Summarize long threads |
| **quota** | Rate limiting per user/chat |
| **export** | Export chat history |
| **webhooks** | Outbound event webhooks |
| **notes** | Quick capture to Obsidian |
