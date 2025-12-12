#!/usr/bin/env bash
set -euo pipefail

# Launchd-friendly startup wrapper for the Telegram agent.
# Loads environment variables, optionally activates a venv, and starts uvicorn.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Optional overrides
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env.local}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"

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

cd "${PROJECT_ROOT}"
exec "${PYTHON_BIN}" -m uvicorn src.main:app --host "${HOST}" --port "${PORT}"
