#!/usr/bin/env bash
set -euo pipefail

# Launchd-friendly startup wrapper for the Telegram agent.
# Loads environment variables, starts the configured tunnel, sets up webhook,
# and starts uvicorn.
#
# Supports TUNNEL_PROVIDER: ngrok (default), cloudflare, tailscale, none

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

# Resolve tunnel provider (default: ngrok for backward compat)
TUNNEL_PROVIDER="${TUNNEL_PROVIDER:-ngrok}"
TUNNEL_PID=""
TUNNEL_URL=""

start_tunnel() {
  case "${TUNNEL_PROVIDER}" in
    ngrok)
      # Kill any existing ngrok processes
      pkill -f "ngrok http" 2>/dev/null || true
      sleep 1

      # Start ngrok in background
      ngrok http "${PORT}" --log=stdout > "${PROJECT_ROOT}/logs/ngrok.log" 2>&1 &
      TUNNEL_PID=$!
      echo "Started ngrok with PID ${TUNNEL_PID}"

      # Wait for ngrok to start and get the public URL
      sleep 3
      for i in {1..10}; do
        TUNNEL_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | "${PYTHON_BIN}" -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'] if d.get('tunnels') else '')" 2>/dev/null || true)
        if [[ -n "${TUNNEL_URL}" ]]; then
          break
        fi
        sleep 1
      done

      if [[ -z "${TUNNEL_URL}" ]]; then
        echo "Failed to get ngrok URL" >&2
        kill ${TUNNEL_PID} 2>/dev/null || true
        exit 1
      fi
      ;;

    cloudflare)
      if [[ -n "${CF_CREDENTIALS_FILE:-}" && -n "${CF_TUNNEL_NAME:-}" ]]; then
        # Named tunnel mode (prod)
        local cf_cmd="cloudflared tunnel"
        if [[ -n "${CF_CONFIG_FILE:-}" ]]; then
          cf_cmd="${cf_cmd} --config ${CF_CONFIG_FILE}"
        fi
        cf_cmd="${cf_cmd} --credentials-file ${CF_CREDENTIALS_FILE} run ${CF_TUNNEL_NAME}"
        ${cf_cmd} > "${PROJECT_ROOT}/logs/cloudflared.log" 2>&1 &
        TUNNEL_PID=$!
        echo "Started cloudflared named tunnel with PID ${TUNNEL_PID}"

        # Named tunnels use WEBHOOK_BASE_URL
        TUNNEL_URL="${WEBHOOK_BASE_URL}"
      else
        # Quick tunnel mode (dev)
        cloudflared tunnel --url "http://localhost:${PORT}" > "${PROJECT_ROOT}/logs/cloudflared.log" 2>&1 &
        TUNNEL_PID=$!
        echo "Started cloudflared quick tunnel with PID ${TUNNEL_PID}"

        # Parse URL from output
        sleep 5
        for i in {1..15}; do
          TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "${PROJECT_ROOT}/logs/cloudflared.log" 2>/dev/null | head -1 || true)
          if [[ -n "${TUNNEL_URL}" ]]; then
            break
          fi
          sleep 1
        done

        if [[ -z "${TUNNEL_URL}" ]]; then
          echo "Failed to get cloudflare tunnel URL" >&2
          kill ${TUNNEL_PID} 2>/dev/null || true
          exit 1
        fi
      fi
      ;;

    tailscale)
      tailscale funnel "${PORT}" > "${PROJECT_ROOT}/logs/tailscale.log" 2>&1 &
      TUNNEL_PID=$!
      echo "Started tailscale funnel with PID ${TUNNEL_PID}"

      sleep 3
      if [[ -n "${TAILSCALE_HOSTNAME:-}" ]]; then
        TUNNEL_URL="https://${TAILSCALE_HOSTNAME}"
      else
        TUNNEL_URL=$(tailscale status --json 2>/dev/null | "${PYTHON_BIN}" -c "import sys,json; d=json.load(sys.stdin); n=d.get('Self',{}).get('DNSName','').rstrip('.'); print(f'https://{n}' if n else '')" 2>/dev/null || true)
      fi

      if [[ -z "${TUNNEL_URL}" ]]; then
        echo "Failed to get tailscale URL" >&2
        kill ${TUNNEL_PID} 2>/dev/null || true
        exit 1
      fi
      ;;

    none|skip)
      echo "No tunnel provider — using WEBHOOK_BASE_URL directly"
      TUNNEL_URL="${WEBHOOK_BASE_URL:-}"
      if [[ -z "${TUNNEL_URL}" ]]; then
        echo "WARNING: No tunnel and no WEBHOOK_BASE_URL set" >&2
      fi
      ;;

    *)
      echo "Unknown TUNNEL_PROVIDER: ${TUNNEL_PROVIDER}" >&2
      exit 1
      ;;
  esac
}

start_tunnel
echo "Tunnel URL: ${TUNNEL_URL}"

# Set up webhook with secret token
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TUNNEL_URL}" ]]; then
  WEBHOOK_URL="${TUNNEL_URL}/webhook"
  echo "Setting webhook to: ${WEBHOOK_URL}"

  # Build webhook URL with secret token if available
  WEBHOOK_PARAMS="url=${WEBHOOK_URL}&drop_pending_updates=true&allowed_updates=%5B%22message%22%2C%22callback_query%22%2C%22poll_answer%22%5D"
  if [[ -n "${TELEGRAM_WEBHOOK_SECRET:-}" ]]; then
    WEBHOOK_PARAMS="${WEBHOOK_PARAMS}&secret_token=${TELEGRAM_WEBHOOK_SECRET}"
    echo "Using webhook secret token"
  fi

  curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?${WEBHOOK_PARAMS}" | "${PYTHON_BIN}" -c "import sys,json; d=json.load(sys.stdin); print('Webhook set!' if d.get('ok') else f'Webhook failed: {d}')"
fi

# Cleanup tunnel on exit
cleanup() {
  echo "Cleaning up tunnel (${TUNNEL_PROVIDER})..."
  if [[ -n "${TUNNEL_PID}" ]]; then
    kill ${TUNNEL_PID} 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Start uvicorn
exec "${PYTHON_BIN}" -m uvicorn src.main:app --host "${HOST}" --port "${PORT}"
