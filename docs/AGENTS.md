# Agents Development Instructions

This document mirrors the expectations in `.claude/CLAUDE.md` but is framed for any agent implementation in this repository.

## Tech Stack
- Python 3.11+
- FastAPI (webhook + admin API)
- python-telegram-bot 21.x
- SQLAlchemy 2.x with SQLite (sqlite-vss extensions)
- LiteLLM for provider routing (OpenAI, Anthropic, Groq, etc.)
- Claude Code SDK for interactive sessions
- Groq Whisper for voice/video transcription
- PIL/Pillow for image work
- structlog for structured logging; pytest for testing

## Project Overview
Telegram bot with multimodal input (text, images, voice, video), Claude Code integration, Obsidian vault operations, and a plugin system. Key abilities:
- Interactive Claude Code sessions with streaming and session persistence
- Spaced repetition (SM-2) for vault ideas
- Design guidance via Impeccable Style, UI Skills, Rams.ai
- Voice/video transcription with LLM correction
- Obsidian vault reading/editing with clickable wikilinks
- Batch collect mode for multi-item processing
- Smart message buffering (2.5s) and reply-context tracking

## Quick Start
```bash
git clone <repo-url>
cd telegram_agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local
python -m src.core.database init
python scripts/start_dev.py start --port 8000
```
Verify with `curl http://localhost:8000/health` and `tail -f logs/app.log`.

### Environment Variables (minimum)
- `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `GROQ_API_KEY`
- Optional: `ANTHROPIC_API_KEY`, `OBSIDIAN_VAULT_PATH`, `TELEGRAM_WEBHOOK_SECRET` (enables header validation), `API_MAX_BODY_BYTES` (body cap for /api,/admin,/webhook)
- `PYTHON_EXECUTABLE` should point to the interpreter used for subprocess calls.

## Development Workflow
- Lint/format before commits: `python -m black src/ tests/ && python -m flake8 src/ tests/ && python -m mypy src/`
- Run tests: `python -m pytest tests/ -v`
- Key dirs: `src/bot/handlers`, `src/services`, `config/modes.yaml`, `tests/`
- Structured logging is mandatory; log every significant step and error.

### Common Commands
- Start full stack (ngrok + webhook): `/opt/homebrew/bin/python3.11 scripts/start_dev.py start --port 8000`
- Webhook management: `python scripts/setup_webhook.py auto-update --port 8000`, `get-webhook`, `validate-bot`
- Tests/coverage: `python -m pytest tests/ --cov=src --cov-report=html`
- Type check: `python -m mypy src/`
- Design skills tooling: `python scripts/manage_design_skills.py show|test|review`
- Proactive tasks: `python -m scripts.proactive_tasks.task_runner list|run <task>`

## Architecture Notes
- Layered flow: Telegram webhook → FastAPI → Bot handlers/CombinedProcessor → Services → DB.
- Plugin system in `src/plugins` with examples under `plugins/` (`claude_code`, `pdf`).
- Message buffering collects messages for 2.5s, then routes via `CombinedMessageProcessor`. Reply context is cached (24h) to preserve conversation threads.
- Modes and settings live in `config/modes.yaml` and are persisted in DB (`src/models/chat.py`).

## Security Practices
- **Secrets & env files**: Keep keys only in `.env.local` (git-ignored). Set file perms to 600; never log tokens or user PII—add redaction filters in `structlog` processors.
- **Webhook hardening (Telegram)**: Always set `secret_token` when configuring the webhook and validate the `X-Telegram-Bot-Api-Secret-Token` header on every request. Prefer `drop_pending_updates=true` on restarts to avoid replayed updates.
- **Transport**: Use HTTPS-only tunnels (ngrok authtoken, no anonymous tunnels). If you expose admin endpoints, enable HSTS and restrict origins to your control plane domain.
- **FastAPI surface**: Require auth (OAuth2/JWT or at least HTTP Basic over TLS) for admin routes; enable CORS allowlist; add rate limiting/request size caps to mitigate flooding.
- **Request size guard**: All `/api`, `/admin`, and `/webhook` routes enforce `API_MAX_BODY_BYTES` (default 1MB via env) using middleware plus endpoint-level checks on `/webhook`.
- **Subprocess calls**: Pass API keys via env vars, not CLI args (avoid `ps` leakage). Clear temp files that may hold user data.
- **Secret scrubbing**: Logging now redacts Telegram tokens, sk-* keys, Groq keys, and JWTs via structlog processor and logging filter. Keep using structured logs; avoid embedding secrets in messages/fields.
- **Production gate**: App will refuse to start in `ENVIRONMENT=production` unless `TELEGRAM_WEBHOOK_SECRET` is set, ensuring webhook auth is always enforced live.
- **SQLite**: Restrict file permissions; set `PRAGMA trusted_schema=OFF` before loading untrusted databases; avoid loading arbitrary extensions; keep backups encrypted if stored off-disk.
- **Dependencies & supply chain**: Pin versions, verify upstream signatures when available, and run `pip install --require-hashes` for production builds. Regularly rotate API keys and delete unused tokens.
- **Logging & monitoring**: Centralize structured logs, scrub secrets, and alert on repeated webhook failures or 429/401 spikes.
- **Least privilege runtime**: Run services under a non-root user; keep ngrok and uvicorn processes scoped to required ports only.

### Subprocess Isolation (Critical)
Running inside uvicorn + python-telegram-bot causes certain async calls to block (Telegram API calls, Claude SDK/httpx, Groq/OpenAI). Always perform external I/O in subprocesses using the configured Python path. Helper functions:
- `run_claude_subprocess()` – `src/services/claude_subprocess.py`
- `send_message_sync()` / `edit_message_sync()` – `src/bot/handlers.py`
- `download_file_sync()` / `transcribe_audio_sync()` – `src/bot/combined_processor.py`
Wrap long operations in `create_tracked_task()` (from `src/utils/task_tracker.py`) instead of `asyncio.create_task()` for graceful shutdown.

## Deployment (launchd)
- Restart after changes: `launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist && launchctl load ...`
- The restart script kills ngrok, restarts uvicorn on port 8847, sets webhook with `drop_pending_updates=true`, and verifies via `getWebhookInfo`.
- Additional services: `com.telegram-agent.health`, `com.telegram-agent.daily-health-review`, `com.telegram-agent.daily-research`.

## Database & Data
- SQLite with vector search extensions in `extensions/`.
- Models under `src/models/`; use Alembic for migrations.
- Key tables: `collect_sessions`, `keyboard_config`, `messages`, `routing_memory`, `claude_sessions`, `chats`.

## Testing Strategy
- Unit tests mock external APIs; integration tests cover end-to-end bot flows.
- Test images live in `tests/fixtures/`.
- Coverage target: >80% (current ~75%).

## Troubleshooting Highlights
- Webhook issues: check ngrok URL/token; `setup_webhook.py validate-bot`.
- Image/voice failures: verify API keys and network.
- DB locks: avoid long transactions; prefer in-memory caches for hot lookups.
- Buffer timing: messages must arrive within 2.5s to combine.

## Known Limitations
- Async blocking without subprocess isolation.
- SQLite contention during buffer callbacks; avoid DB writes in that timer when possible.
- Design skills trigger via keyword detection only; no visual validation.
- SRS is local to the device/database.

## Contributor Checklist
1. Follow structured logging everywhere.
2. Use subprocess helpers for external I/O.
3. Add tests for new behaviors.
4. Update docs (including this AGENTS.md) when workflows or commands change.
