#!/bin/sh
set -e

# Verity — single-command install
# Usage: ./install.sh [--setup] [--no-start]
#   --setup     Force re-run of setup wizard even if .env exists
#   --no-start  Install only, don't start the bot

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

# --- Colors (with fallback) ---
if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null)" -ge 8 ] 2>/dev/null; then
    BOLD=$(tput bold)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    RESET=$(tput sgr0)
else
    BOLD="" GREEN="" YELLOW="" RED="" RESET=""
fi

info()  { printf "%s[*]%s %s\n" "$GREEN"  "$RESET" "$1"; }
warn()  { printf "%s[!]%s %s\n" "$YELLOW" "$RESET" "$1"; }
error() { printf "%s[x]%s %s\n" "$RED"    "$RESET" "$1"; }

# --- Parse flags ---
FORCE_SETUP=0
NO_START=0
for arg in "$@"; do
    case "$arg" in
        --setup)    FORCE_SETUP=1 ;;
        --no-start) NO_START=1 ;;
        --help|-h)
            printf "Usage: ./install.sh [--setup] [--no-start]\n"
            printf "  --setup     Force re-run of setup wizard\n"
            printf "  --no-start  Install only, don't start the bot\n"
            exit 0
            ;;
        *) warn "Unknown flag: $arg" ;;
    esac
done

# --- 1. Find Python >= 3.10 ---
find_python() {
    for cmd in python3.11 python3.12 python3.13 python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ver=$("$cmd" --version 2>&1 | sed 's/Python //')
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] 2>/dev/null && [ "$minor" -ge "$MIN_PYTHON_MINOR" ] 2>/dev/null; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

info "Looking for Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}..."
PYTHON_CMD=$(find_python) || {
    error "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ not found."
    error "Install it from https://www.python.org/downloads/ and re-run this script."
    exit 1
}
PYTHON_VER=$("$PYTHON_CMD" --version 2>&1)
info "Found $PYTHON_VER ($(command -v "$PYTHON_CMD"))"

# --- 2. Create/reuse venv ---
if [ -d "$VENV_DIR" ] && [ -x "$VENV_DIR/bin/python" ]; then
    info "Virtual environment exists at .venv — reusing"
else
    info "Creating virtual environment at .venv..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    info "Virtual environment created"
fi
# Always use the venv python from here on
PIP="$VENV_DIR/bin/pip"
PYTHON="$VENV_DIR/bin/python"

# --- 3. Install dependencies ---
info "Installing dependencies..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r "$REPO_DIR/requirements.txt"
info "Dependencies installed"

# --- 4. Setup wizard ---
if [ "$FORCE_SETUP" -eq 1 ] || [ ! -f "$REPO_DIR/.env" ]; then
    info "Running setup wizard..."
    "$PYTHON" "$REPO_DIR/scripts/setup_wizard.py"
else
    info "Config .env exists — skipping wizard (use --setup to re-run)"
fi

# --- 5. Start bot ---
if [ "$NO_START" -eq 1 ]; then
    info "Install complete. Start with: .venv/bin/python scripts/start_dev.py start --port 8000"
else
    info "Starting bot..."
    exec "$PYTHON" "$REPO_DIR/scripts/start_dev.py" start --port 8000
fi
