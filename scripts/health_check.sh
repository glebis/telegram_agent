#!/usr/bin/env bash
set -euo pipefail

# Health check for the Telegram agent.
# - Verifies the local HTTP health endpoint.
# - Verifies Telegram webhook status (requires TELEGRAM_BOT_TOKEN).
# - On webhook issues, attempts automatic recovery before restarting.
# - On local service failure, requests launchd restart.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.11}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
TIMEOUT="${TIMEOUT:-5}"
SERVICE_LABEL="${SERVICE_LABEL:-com.telegram-agent.bot}"
HEALTH_URL="${HEALTH_URL:-http://${HOST}:${PORT}/health}"
WEBHOOK_RECOVERY_SCRIPT="${SCRIPT_DIR}/webhook_recovery.py"
HEALTH_ALERT_SCRIPT="${SCRIPT_DIR}/health_alert.py"

# Load env file if present
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

local_status=0
webhook_status=0

# 1) Local health endpoint (retry once after 10s to handle startup/transient issues)
health_json="$(curl -fsS --max-time "${TIMEOUT}" "${HEALTH_URL}" || true)"
if [[ -z "${health_json}" ]]; then
  echo "Health endpoint did not respond, retrying in 10s: ${HEALTH_URL}" >&2
  sleep 10
  health_json="$(curl -fsS --max-time "${TIMEOUT}" "${HEALTH_URL}" || true)"
fi
if [[ -z "${health_json}" ]]; then
  echo "Health endpoint did not respond after retry: ${HEALTH_URL}" >&2
  local_status=1
else
  if ! "${PYTHON_BIN}" - <<'PY' "${health_json}"; then
import json, sys
try:
    payload = json.loads(sys.argv[1])
except Exception:
    sys.stderr.write("Failed to parse health JSON\n")
    sys.exit(1)

# Check bot_initialized first - this catches half-started state
if not payload.get("bot_initialized", False):
    sys.stderr.write("Bot lifespan not fully initialized\n")
    sys.exit(1)

if payload.get("status") != "healthy":
    error_details = payload.get("error_details") or {}
    sys.stderr.write(f"Status: {payload.get('status')}, errors: {error_details}\n")
    sys.exit(1)
PY
    echo "Health endpoint returned non-healthy status" >&2
    local_status=1
  fi
fi

# 2) Telegram webhook status (only if local service is healthy)
if [[ "${local_status}" -eq 0 && -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  webhook_json="$(curl -fsS --max-time "${TIMEOUT}" "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" || true)"
  if [[ -z "${webhook_json}" ]]; then
    echo "Failed to fetch Telegram webhook info" >&2
    webhook_status=1
  else
    if ! "${PYTHON_BIN}" - <<'PY' "${webhook_json}"; then
import json, sys

data = json.loads(sys.argv[1])

if not data.get("ok"):
    sys.exit(1)

result = data.get("result") or {}
url = result.get("url") or ""

# Require webhook to be set
if not url:
    sys.stderr.write("Telegram webhook not set\n")
    sys.exit(1)

# Fail on RECENT Telegram delivery errors (within last 5 minutes)
import time
last_err = result.get("last_error_date") or 0
if last_err and (time.time() - last_err) < 300:
    msg = result.get("last_error_message") or "Telegram reports last_error"
    sys.stderr.write(f"Webhook error (recent): {msg}\n")
    sys.exit(1)

# Warn on high pending count (but don't fail immediately)
pending = result.get("pending_update_count", 0)
if pending > 10:
    sys.stderr.write(f"High pending update count: {pending}\n")
    sys.exit(1)
PY
      webhook_status=1
    fi
  fi
fi

# Helper: send health alert (non-blocking, best-effort)
send_health_alert() {
  local alert_type="$1"  # --failure "reason" or --success
  if [[ -f "${HEALTH_ALERT_SCRIPT}" ]]; then
    "${PYTHON_BIN}" "${HEALTH_ALERT_SCRIPT}" ${alert_type} 2>/dev/null || true
  fi
}

# 3) Handle failures
if [[ "${local_status}" -ne 0 ]]; then
  # Local service is unhealthy - alert and restart
  send_health_alert "--failure \"Health endpoint unreachable or unhealthy\""
  echo "Local service unhealthy; requesting launchd restart for ${SERVICE_LABEL}" >&2
  if command -v launchctl >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$(id -u)/${SERVICE_LABEL}" || true
  fi
  exit 1
fi

if [[ "${webhook_status}" -ne 0 ]]; then
  # Webhook issue detected - alert and try recovery
  send_health_alert "--failure \"Webhook check failed\""
  echo "Webhook issue detected; attempting automatic recovery..." >&2

  if [[ -x "${WEBHOOK_RECOVERY_SCRIPT}" ]]; then
    export ENV_FILE
    if "${PYTHON_BIN}" "${WEBHOOK_RECOVERY_SCRIPT}"; then
      echo "Webhook recovery successful" >&2
      send_health_alert "--success"
      exit 0
    else
      echo "Webhook recovery failed; requesting service restart" >&2
      if command -v launchctl >/dev/null 2>&1; then
        launchctl kickstart -k "gui/$(id -u)/${SERVICE_LABEL}" || true
      fi
      exit 1
    fi
  else
    echo "Webhook recovery script not found or not executable: ${WEBHOOK_RECOVERY_SCRIPT}" >&2
    # Fall back to restart
    if command -v launchctl >/dev/null 2>&1; then
      launchctl kickstart -k "gui/$(id -u)/${SERVICE_LABEL}" || true
    fi
    exit 1
  fi
fi

# All checks passed — notify recovery if there were previous failures
send_health_alert "--success"
exit 0
