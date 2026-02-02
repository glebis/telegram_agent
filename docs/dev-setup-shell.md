# Interactive Shell Setup (Non-Docker)

A concise, repeatable setup for running Telegram Agent directly on macOS/Linux.

## Quick Start: Interactive Wizard

The fastest way to get set up:

```bash
git clone https://github.com/glebis/telegram_agent.git
cd telegram_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_wizard.py
```

The wizard walks through all configuration interactively:
1. Pre-flight checks (Python version, dependencies, directories)
2. Core config (bot token, webhook secret, environment profile)
3. API keys (OpenAI, Groq, Anthropic - all optional)
4. Optional features (Obsidian vault, Claude Code work dir)
5. Database initialization
6. Verification and summary

After the wizard completes:
```bash
python scripts/start_dev.py start --port 8000
```

## Manual Setup

If you prefer manual configuration or need finer control:

### Prerequisites
- Python 3.11+
- git, curl, sqlite3, pip
- Optional: ngrok or cloudflared (webhook tunnel); marker_single (PDF->MD)

### 1) Clone and virtualenv
```bash
git clone https://github.com/glebis/telegram_agent.git
cd telegram_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 2) Install dependencies
```bash
pip install -r requirements.txt
```

### 3) Configure environment
```bash
cp .env.example .env.local
```
Set at minimum:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `OPENAI_API_KEY` (or other LLM keys)
- `DATABASE_URL` (default SQLite is fine)

Optional:
- `OBSIDIAN_VAULT_PATH` - path to your Obsidian vault
- `GROQ_API_KEY` - for voice transcription
- `ANTHROPIC_API_KEY` - for Claude Code integration
- `SQLITE_EXTENSIONS_PATH` (directory containing vector0/vss0)

### 4) Initialize database (optional; auto on first run)
```bash
python - <<'PY'
import asyncio
from src.core.database import init_database
asyncio.run(init_database())
PY
```

### 5) Run API/bot (dev)
```bash
python scripts/start_dev.py start --port 8000
```
Or manually:
```bash
uvicorn src.main:app --reload --port 8000 --host 0.0.0.0
```

### 6) Set webhook (pick one)
- With tunnel (ngrok/cloudflared) pointing to port 8000:
```bash
python - <<'PY'
import asyncio, os
from src.utils.ngrok_utils import WebhookManager
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
base = os.getenv("WEBHOOK_BASE_URL")  # e.g., https://xxxx.ngrok-free.app
secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
wm = WebhookManager(bot_token)
async def main():
    ok, msg = await wm.set_webhook(f"{base}/webhook", secret)
    print(ok, msg)
asyncio.run(main())
PY
```
- Or via Telegram API directly:
```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d url="${WEBHOOK_BASE_URL}/webhook" \
  -d secret_token="${TELEGRAM_WEBHOOK_SECRET}"
```

### 7) Worker (optional background jobs)
```bash
python scripts/worker_queue.py --once   # or --interval 10
```
Env overrides:
- `JOB_QUEUE_DIR` (default: ~/agent_tasks)
- `JOB_QUEUE_LOG_DIR` (default: ./logs)

### 8) Health check
```bash
curl -s http://localhost:8000/health
```

## Re-running Setup

The wizard is idempotent. Run it again to update any configuration:
```bash
python scripts/setup_wizard.py
```
Existing values are preserved; you can update individual fields without re-entering everything.

## Tips
- Quick env load: `set -a; source .env.local; set +a`
- If sqlite-vss isn't available, the app falls back gracefully (vector search disabled).
- For polling-only debugging, you can wire a small runner that calls `bot.application.run_polling()` instead of webhooks.
- Wizard saves to `.env.local` by default. Override with `--env-file /path/to/.env`.
