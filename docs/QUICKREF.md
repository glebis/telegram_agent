# Quick Reference

## Essential Commands

### Development
```bash
# Start bot (production-like with ngrok)
/opt/homebrew/bin/python3.11 scripts/start_dev.py start --port 8847

# Format & lint
python -m black src/ tests/ && python -m flake8 src/ tests/ && python -m isort src/ tests/

# Run tests
pytest -v

# Type check
mypy src/
```

### Production Service
```bash
# Restart bot service
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist && \
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist

# Check status
launchctl list | grep telegram && tail -10 logs/app.log

# View logs
tail -f logs/app.log
tail -f logs/launchd_health.log
```

### Debugging
```bash
# Database queries
sqlite3 data/telegram_agent.db "SELECT session_id, chat_id, is_active FROM claude_sessions ORDER BY last_used DESC LIMIT 5;"
sqlite3 data/telegram_agent.db "SELECT chat_id, name, active FROM admin_contacts;"
sqlite3 data/telegram_agent.db "SELECT chat_id, claude_mode FROM chats WHERE claude_mode = 1;"

# Check webhook
source .env && curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool

# Recover webhook
ENV_FILE=.env python3 scripts/webhook_recovery.py

# Watch buffering
grep -E "Buffered|Flushing|combined" logs/app.log | tail -20
```

## File Locations

### Core Services
- **Claude Code**: `src/services/claude_code_service.py`, `src/services/claude_subprocess.py`
- **Voice/Video**: `src/services/voice_service.py`, `src/services/transcript_corrector.py`
- **Vault Operations**: `src/services/vault_user_service.py`, `src/services/link_service.py`
- **Buffering**: `src/services/message_buffer.py`
- **Reply Context**: `src/services/reply_context.py`
- **Collect Mode**: `src/services/collect_service.py`

### Handlers (Modular)
- **Core**: `src/bot/handlers/core_commands.py` - /start, /help, /settings
- **Claude**: `src/bot/handlers/claude_commands.py` - /claude:* commands
- **Collect**: `src/bot/handlers/collect_commands.py` - /collect:* commands
- **Notes**: `src/bot/handlers/note_commands.py` - /note command
- **Modes**: `src/bot/handlers/mode_commands.py` - /mode, /analyze, /coach

### Configuration
- **Modes**: `config/modes.yaml`
- **ngrok**: `config/ngrok.yml`
- **Environment**: `.env` or `.env.local`

### Database Tables
- `chats` - User settings (claude_mode, show_model_buttons, claude_model)
- `claude_sessions` - Claude session persistence
- `admin_contacts` - Authorized Claude users
- `collect_sessions` - Batch collection state
- `keyboard_config` - Dynamic keyboards
- `messages` - Message history

## Architecture Patterns

### Subprocess Isolation
**Why**: Certain async operations block in webhook context (Telegram API, Claude SDK, httpx)
**Solution**: Execute in subprocess with fresh event loop

**Helper Functions**:
- `send_message_sync()` - Send Telegram messages
- `edit_message_sync()` - Edit Telegram messages
- `download_file_sync()` - Download Telegram files
- `run_claude_subprocess()` - Execute Claude queries
- `transcribe_audio_sync()` - Transcribe audio

### Background Tasks
**Use tracked tasks for graceful shutdown**:
```python
from src.utils.task_tracker import create_tracked_task

create_tracked_task(run_claude(), name="claude_execution")
```

### Reply Context
1. Extract content from `reply_to_message` (text, captions, media type)
2. Check cache for existing ReplyContext
3. If miss, create context from extracted content
4. Build prompt with original message + response
5. Send to Claude with full context

### Message Buffering
1. Collect messages per (chat_id, user_id)
2. 2.5 second timeout after last message
3. Flush buffer to CombinedMessageProcessor
4. Route to appropriate handler
5. Execute in background task

## Recent Features (Last 2 Weeks)

| Feature | Date | Description |
|---------|------|-------------|
| Enhanced Reply Context | Jan 18 | Extract full context from reply_to_message for all types |
| Transcript Correction | Jan 11 | LLM-based correction with configurable levels |
| Auto-forward Voice | Jan 11 | Forward voice to Claude in locked mode |
| Model Settings | Jan 11 | Toggle model buttons, set default model |
| Launchd Service | Jan 8 | System service configuration |
| Worker Queue | Jan 5 | Background job processing |
| Modular Handlers | Jan 1 | Split handlers into focused modules |

## Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| Webhook not receiving | ngrok URL changed | Run `webhook_recovery.py` or wait for health monitor |
| Claude stuck | Session not responding | `/claude:reset` to kill processes |
| Voice not transcribing | Groq API key missing | Check `GROQ_API_KEY` in `.env` |
| Notes not found | Vault path wrong | Check `OBSIDIAN_VAULT_PATH` in `.env` |
| Buffering not working | Timeout too short | Messages must arrive within 2.5 seconds |
| Async operations block | Webhook context issue | Use subprocess helpers or background tasks |

## Environment Variables

**Required**:
- `TELEGRAM_BOT_TOKEN` - Bot token from @BotFather
- `TELEGRAM_WEBHOOK_SECRET` - Secret for webhook validation
- `OPENAI_API_KEY` - For LLM services
- `GROQ_API_KEY` - For voice transcription

**Optional**:
- `OBSIDIAN_VAULT_PATH` - Path to vault (default: ~/Research/vault)
- `OBSIDIAN_VAULT_NAME` - Vault name (default: vault)
- `NGROK_PORT` - Port for ngrok (default: 8847)
- `LOG_LEVEL` - Logging level (default: INFO)
- `PYTHON_EXECUTABLE` - Python path (default: /opt/homebrew/bin/python3.11)

## Plugin Development

1. Create `plugins/my_plugin/plugin.yaml`:
```yaml
name: my_plugin
version: 0.1.0
description: My plugin
author: Me
enabled: true
```

2. Create `plugins/my_plugin/plugin.py`:
```python
from src.plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    async def on_load(self):
        self.logger.info("Plugin loaded")

    def get_command_handlers(self):
        return {
            "mycommand": self.handle_command
        }

    async def handle_command(self, update, context):
        await update.message.reply_text("Hello from plugin!")
```

3. Restart bot to load plugin

See `plugins/claude_code/` for reference implementation.
