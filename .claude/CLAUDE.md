# Verity

See @docs/ARCHITECTURE.md for system design, @docs/CONTRIBUTING.md for dev setup.

## Tech Stack
Python 3.11+, FastAPI, python-telegram-bot 21.x, SQLAlchemy 2.x (async), SQLite + sqlite-vss, LiteLLM, Claude Code SDK, Groq Whisper, standard `logging` module, pytest.

## CRITICAL: Subprocess Isolation

External I/O **blocks indefinitely** in the webhook handler context (uvicorn → FastAPI → python-telegram-bot nested event loop). ALL Telegram API calls, Claude SDK queries, and HTTP requests must use subprocess isolation.

Use existing helpers — never call these APIs directly in handler code:
- `send_message_sync()` / `edit_message_sync()` — `src/bot/handlers.py`
- `download_file_sync()` / `transcribe_audio_sync()` — `src/bot/combined_processor.py`
- `run_claude_subprocess()` — `src/services/claude_subprocess.py`

For long-running work, use `create_tracked_task()` from `src/utils/task_tracker.py` (not `asyncio.create_task()`).

## Rules
1. Run linting before committing: `python -m black src/ tests/ && python -m flake8 src/ tests/ && python -m isort src/ tests/`
2. Run tests after changes: `python -m pytest tests/ -v` (focused: `pytest tests/path/to/test.py -v`)
3. Log with standard `logging` module: `logging.getLogger(__name__)`
4. When adding/removing commands, update `/help` in `src/bot/handlers/core_commands.py` → `help_command()`
5. When inserting new top-level YAML sections in config files, verify you're not splitting an existing section — indentation determines structure
6. Hooks run automatically:
   - `.claude/hooks/auto-format-python.sh` — after editing .py files (Black + isort)
   - `.claude/hooks/pre-commit-tests.sh` — before `git commit` (flake8 + Black check + mypy + pytest)
   - `.claude/hooks/run-contact-tests.sh` — after editing `message_handlers.py` or `callback_handlers.py`
   - `.claude/hooks/validate-defaults-yaml.sh` — after editing config YAML or `config.py`/`defaults_loader.py`
7. **Web fetching priority chain**: `gh` CLI for any GitHub URL (PRs, issues, APIs) → `WebFetch` for public web pages → Firecrawl skill when WebFetch fails or returns truncated content → `tavily-search` skill for broad research across multiple sources. Never use `curl` in Bash for fetching web content when a dedicated tool exists.
   <!-- Prevents: using WebFetch on GitHub URLs (fails on auth), using curl in Bash (bypasses tool visibility), reaching for tavily-search when a single known URL just needs WebFetch -->
8. **Git branch discipline**: Create a `feature/` or `fix/` branch before any commit that adds or changes functionality. Only commit directly to `main` for one-file chores (gitignore, typo, config). Always check `git branch --show-current` before your first commit in a session. Never amend a commit that's already on a remote branch.
   <!-- Prevents: feature work landing directly on main (hard to revert/review), losing track of which branch you're on, amending pushed commits (force-push risk) -->
9. **Scope of changes**: Only modify files directly required by the task. Do not refactor adjacent code, add type hints to unchanged functions, update unrelated imports, or "improve" nearby logic. If you discover an unrelated bug or improvement, note it in a comment to the user — do not fix it in the same branch.
   <!-- Prevents: bloated diffs that obscure the real change, unreviewed drive-by edits, merge conflicts with parallel work, breaking unrelated code paths -->

## Commands
```bash
# Start bot (includes ngrok + webhook setup)
/opt/homebrew/bin/python3.11 scripts/start_dev.py start --port 8000

# Lint, type-check, test
python -m black src/ tests/ && python -m flake8 src/ tests/ && python -m isort src/ tests/
python -m mypy src/
python -m pytest tests/ -v

# Restart production (auto-handles ngrok + webhook + drop_pending_updates)
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist && \
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist
# Verify: sleep 5 && launchctl list | grep telegram && tail -10 logs/app.log

# Webhook status
source .env && curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
```

## Key Directories
- `src/bot/handlers/` — Command handlers (new commands here)
- `src/services/` — Business logic (new features here)
- `src/models/` — SQLAlchemy ORM models
- `config/` — YAML configs (modes, settings, defaults, design_skills)
- `plugins/` — Plugin directory (claude_code, pdf)
- `scripts/proactive_tasks/` — Scheduled task framework

## Code Patterns
```python
# Config
from src.core.config import get_settings
settings = get_settings()

# Database
from src.core.database import get_db_session
async with get_db_session() as session: ...

# Background tasks
from src.utils.task_tracker import create_tracked_task
create_tracked_task(coroutine, name="task_name")

# Logging
import logging
logger = logging.getLogger(__name__)
```

## Conventions
- Vault note references: use full absolute paths (`/Users/server/Research/vault/...`) — auto-converted to clickable Obsidian deep links
- Code style: Black 88 chars, isort, mypy, Google-style docstrings
- Git: conventional commits, branches `feature/` or `fix/`

## Issue Tracking
Issues are tracked in [Beads](https://github.com/synthase/beads) (`.beads/beads.db`), not GitHub Issues. Use `/bd` in Telegram or query the DB directly. GitHub issues are closed and synced to beads.

## Production Services
All plists in `~/Library/LaunchAgents/`. Restart script: `scripts/run_agent_launchd.sh`.
- `com.telegram-agent.bot` — Main bot (port 8847)
- `com.telegram-agent.health` — Health monitor
- `com.telegram-agent.daily-health-review` — 9:30 AM
- `com.telegram-agent.daily-research` — 10:00 AM
