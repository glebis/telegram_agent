# Interactive Shell Setup (Non-Docker)

A concise, repeatable setup for running Telegram Agent directly on macOS/Linux.

## Prerequisites
- Python 3.11+
- git, curl, sqlite3, pip
- Optional: ngrok or cloudflared (webhook tunnel); marker_single (PDF→MD)

## 1) Clone and virtualenv
```bash
git clone https://github.com/glebis/telegram_agent.git
cd telegram_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 2) Install dependencies
```bash
pip install -r requirements.txt
# optional dev tooling
# pip install -r requirements-dev.txt
```

## 3) Configure environment
```bash
cp .env.example .env
```
Set at minimum:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `OPENAI_API_KEY` (or other LLM keys)
- `DATABASE_URL` (default SQLite is fine)
Optional:
- `SQLITE_EXTENSIONS_PATH` (directory containing vector0/vss0)
- `SQLITE_EXTENSION_SUFFIX` (.so/.dylib/.dll if non-standard)

## 4) Initialize database (optional; auto on first run)
```bash
python - <<'PY'
import asyncio
from src.core.database import init_database
asyncio.run(init_database())
PY
```

## 5) Run API/bot (dev)
```bash
uvicorn src.main:app --reload --port 8000 --host 0.0.0.0
```

## 6) Set webhook (pick one)
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

## 7) Worker (optional background jobs)
```bash
python worker_queue.py --once   # or --interval 10
```
Env overrides:
- `JOB_QUEUE_DIR` (default: ~/agent_tasks)
- `JOB_QUEUE_LOG_DIR` (default: ./logs)

## 8) Health check
```bash
curl -s http://localhost:8000/health
```

## Tips
- Quick env load: `set -a; source .env; set +a`
- If sqlite-vss isn’t available, the app falls back gracefully (vector search disabled).
- For polling-only debugging, you can wire a small runner that calls `bot.application.run_polling()` instead of webhooks.
