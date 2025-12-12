#!/usr/bin/env bash
set -euo pipefail

# Health check for the Telegram agent.
# - Verifies the local HTTP health endpoint.
# - Optionally verifies Telegram webhook status (requires TELEGRAM_BOT_TOKEN).
# - On failure, will request launchd to restart the service.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env.local}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
TIMEOUT="${TIMEOUT:-5}"
SERVICE_LABEL="${SERVICE_LABEL:-com.telegram-agent.bot}"
HEALTH_URL="${HEALTH_URL:-http://${HOST}:${PORT}/health}"

# Load env file if present
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

status=0

# 1) Local health endpoint
health_json="$(curl -fsS --max-time "${TIMEOUT}" "${HEALTH_URL}" || true)"
if [[ -z "${health_json}" ]]; then
  echo "Health endpoint did not respond: ${HEALTH_URL}" >&2
  status=1
else
  if ! "${PYTHON_BIN}" - <<'PY' "${health_json}"; then
import json, sys
try:
    payload = json.loads(sys.argv[1])
except Exception:
    sys.exit(1)
if payload.get("status") != "healthy":
    sys.exit(1)
PY
    echo "Health endpoint returned non-healthy status" >&2
    status=1
  fi
fi

# 2) Telegram webhook status (optional)
if [[ "${status}" -eq 0 && -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  webhook_json="$(curl -fsS --max-time "${TIMEOUT}" "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" || true)"
  if [[ -z "${webhook_json}" ]]; then
    echo "Failed to fetch Telegram webhook info" >&2
    status=1
  else
    if ! "${PYTHON_BIN}" - <<'PY' "${webhook_json}" "${TELEGRAM_WEBHOOK_URL:-}"; then
import json, sys

data = json.loads(sys.argv[1])
expected_url = sys.argv[2]

if not data.get("ok"):
    sys.exit(1)

result = data.get("result") or {}
url = result.get("url") or ""

# Require webhook to be set
if not url:
    sys.stderr.write("Telegram webhook not set\n")
    sys.exit(1)

# If expected_url provided, ensure it matches (prefix match allows ngrok params)
if expected_url and not url.startswith(expected_url):
    sys.stderr.write(f"Webhook URL mismatch: got '{url}', expected prefix '{expected_url}'\n")
    sys.exit(1)

# Fail on reported Telegram delivery errors
if result.get("last_error_date"):
    msg = result.get("last_error_message") or "Telegram reports last_error"
    sys.stderr.write(msg + "\n")
    sys.exit(1)
PY
      status=1
    fi
  fi
fi

if [[ "${status}" -ne 0 ]]; then
  echo "Health check failed; requesting launchd restart for ${SERVICE_LABEL}" >&2
  if command -v launchctl >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$(id -u)/${SERVICE_LABEL}" || true
  fi
  exit "${status}"
fi
