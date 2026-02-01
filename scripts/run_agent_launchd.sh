#!/usr/bin/env bash
set -euo pipefail

# Launchd-friendly startup wrapper for the Telegram agent.
# Loads environment variables, starts ngrok, sets up webhook, and starts uvicorn.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Optional overrides
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env.local}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Activate venv if provided
if [[ -n "${VENV_PATH:-}" && -x "${VENV_PATH}/bin/activate" ]]; then
  # shellcheck disable=SC1090
  source "${VENV_PATH}/bin/activate"
fi

# Load env file if present (silently skip if missing)
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

# Also load .env if .env.local doesn't exist
if [[ ! -f "${ENV_FILE}" && -f "${PROJECT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${PROJECT_ROOT}/.env"
  set +a
fi

cd "${PROJECT_ROOT}"

# Kill any existing ngrok processes
pkill -f "ngrok http" 2>/dev/null || true
sleep 1

# Start ngrok in background
ngrok http "${PORT}" --log=stdout > "${PROJECT_ROOT}/logs/ngrok.log" 2>&1 &
NGROK_PID=$!
echo "Started ngrok with PID ${NGROK_PID}"

# Wait for ngrok to start and get the public URL
sleep 3
NGROK_URL=""
for i in {1..10}; do
  NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | "${PYTHON_BIN}" -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'] if d.get('tunnels') else '')" 2>/dev/null || true)
  if [[ -n "${NGROK_URL}" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "${NGROK_URL}" ]]; then
  echo "Failed to get ngrok URL" >&2
  kill ${NGROK_PID} 2>/dev/null || true
  exit 1
fi

echo "ngrok URL: ${NGROK_URL}"

# Set up webhook with secret token
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  WEBHOOK_URL="${NGROK_URL}/webhook"
  echo "Setting webhook to: ${WEBHOOK_URL}"

  # Build webhook URL with secret token if available
  WEBHOOK_PARAMS="url=${WEBHOOK_URL}&drop_pending_updates=true&allowed_updates=%5B%22message%22%2C%22callback_query%22%2C%22poll_answer%22%5D"
  if [[ -n "${TELEGRAM_WEBHOOK_SECRET:-}" ]]; then
    WEBHOOK_PARAMS="${WEBHOOK_PARAMS}&secret_token=${TELEGRAM_WEBHOOK_SECRET}"
    echo "Using webhook secret token"
  fi

  curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?${WEBHOOK_PARAMS}" | "${PYTHON_BIN}" -c "import sys,json; d=json.load(sys.stdin); print('Webhook set!' if d.get('ok') else f'Webhook failed: {d}')"
fi

# Cleanup ngrok on exit
cleanup() {
  echo "Cleaning up ngrok..."
  kill ${NGROK_PID} 2>/dev/null || true
}
trap cleanup EXIT

# Start uvicorn
exec "${PYTHON_BIN}" -m uvicorn src.main:app --host "${HOST}" --port "${PORT}"
