# Claude Development Instructions

## Tech Stack
- Python 3.11+, FastAPI, python-telegram-bot 21.x, SQLAlchemy 2.x (async), SQLite + sqlite-vss
- LiteLLM for LLM calls, Claude Code SDK, Groq Whisper for transcription
- structlog for logging, pydantic-settings for config, pytest for tests

## CRITICAL: Async Blocking — Subprocess Isolation Pattern

The bot runs inside uvicorn → FastAPI → python-telegram-bot. This nested event loop context causes async operations to **block indefinitely**. ALL external I/O must use subprocess isolation.

**Operations that BLOCK in webhook handler context:**
- `context.bot.get_file()`, `context.bot.send_message()`, `message.edit_text()`
- Claude Code SDK `query()`, `httpx.AsyncClient`, Groq/OpenAI API calls

**Solution:** Run blocking I/O in subprocesses for a fresh event loop:
```python
from src.core.config import get_settings
python_path = get_settings().python_executable
subprocess.run([python_path, "-c", script], capture_output=True, text=True, timeout=30)
```

**Subprocess helpers:**
| Function | Location |
|----------|----------|
| `send_message_sync()` | `src/bot/handlers.py` |
| `edit_message_sync()` | `src/bot/handlers.py` |
| `download_file_sync()` | `src/bot/combined_processor.py` |
| `run_claude_subprocess()` | `src/services/claude_subprocess.py` |
| `transcribe_audio_sync()` | `src/bot/combined_processor.py` |

**Background tasks:** Use `create_tracked_task()` from `src/utils/task_tracker.py` instead of `asyncio.create_task()` for graceful shutdown support.

## Before Making Changes
1. Always run linting and fix errors before building
2. Run tests to ensure nothing is broken
3. Use structured logging (structlog) — log all actions
4. Update /help when adding new commands — lives in `src/bot/handlers/core_commands.py` → `help_command()`
5. Run contact handler tests when modifying `src/bot/message_handlers.py` or `src/bot/callback_handlers.py` — hook at `.claude/hooks/run-contact-tests.sh` does this automatically
6. Run config validation tests when editing `config/defaults.yaml`, `config/settings.yaml`, `config/profiles/*.yaml`, `src/core/config.py`, or `src/core/defaults_loader.py` — hook at `.claude/hooks/validate-defaults-yaml.sh` does this automatically. When inserting new top-level YAML sections, verify you're not splitting an existing section in half

## Commands
```bash
# Start bot (preferred — includes ngrok + webhook)
/opt/homebrew/bin/python3.11 scripts/start_dev.py start --port 8000

# Lint & format
python -m black src/ tests/ && python -m flake8 src/ tests/ && python -m isort src/ tests/

# Type check
python -m mypy src/

# Test
python -m pytest tests/ -v

# Restart production service
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist && \
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist
# Verify: sleep 5 && launchctl list | grep telegram && tail -10 logs/app.log

# Webhook debug
source .env && curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool

# Database queries
sqlite3 data/telegram_agent.db ".tables"
```

## Architecture
```
Telegram API → FastAPI → Bot Handlers → Combined Processor → Services → Database
                     ↓                         ↓
                 Admin API              Plugin Router
```

- **Message buffering**: 2.5s timeout combines multi-part messages (`src/services/message_buffer.py`)
- **Reply context**: Tracks message origins for reply-to-continue (`src/services/reply_context.py`)
- **Plugin system**: `src/plugins/base.py` + `src/plugins/manager.py`, user plugins in `plugins/`
- **Mode system**: `config/modes.yaml` + `src/core/mode_manager.py`
- **Config**: `src/core/config.py` via `get_settings()`

## Key Directories
- `src/bot/handlers/` — Command handlers (new commands go here)
- `src/services/` — Business logic (new features go here)
- `src/models/` — SQLAlchemy ORM models
- `config/` — YAML configs (modes, settings, design_skills, defaults)
- `plugins/` — Plugin directory (claude_code, pdf)
- `scripts/proactive_tasks/` — Scheduled task framework
- `tests/` — Test suite

## Code Patterns
```python
# Config access
from src.core.config import get_settings
settings = get_settings()

# Database
from src.core.database import get_db_session
async with get_db_session() as session: ...

# Background tasks (NOT asyncio.create_task)
from src.utils.task_tracker import create_tracked_task
create_tracked_task(run_claude(), name="claude_execution")

# Logging
import structlog
logger = structlog.get_logger(__name__)
```

## Obsidian Integration
When referencing vault notes in Claude responses, use full absolute paths — the bot auto-converts to clickable deep links:
```
GOOD: /Users/server/Research/vault/Research/Notes/Mem0.md
BAD:  Research/Notes/Mem0.md
```

## Production Services
- `~/Library/LaunchAgents/com.telegram-agent.bot.plist` — Main bot (port 8847)
- `~/Library/LaunchAgents/com.telegram-agent.health.plist` — Health monitor
- `~/Library/LaunchAgents/com.telegram-agent.daily-health-review.plist` — 9:30 AM
- `~/Library/LaunchAgents/com.telegram-agent.daily-research.plist` — 10:00 AM
- Restart script (`scripts/run_agent_launchd.sh`) auto-handles ngrok + webhook + `drop_pending_updates=true`

## Code Style
- Black (88 chars), isort, mypy, Google-style docstrings
- Conventional commits, branch naming: `feature/` or `fix/`
