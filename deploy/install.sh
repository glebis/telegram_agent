#!/usr/bin/env bash
# install.sh -- Set up the Telegram Agent as a systemd service on Linux.
#
# Usage:
#   sudo bash deploy/install.sh [INSTALL_DIR]
#
# Default INSTALL_DIR: /opt/telegram-agent
#
# What this script does:
#   1. Creates a dedicated "telegram-agent" system user (no login shell).
#   2. Copies the project to INSTALL_DIR (if not already there).
#   3. Creates a Python virtual environment and installs dependencies.
#   4. Creates /etc/telegram-agent/ for the environment file.
#   5. Installs and enables the systemd service.
#   6. Starts the service and prints status.
#
# Prerequisites:
#   - Python 3.11+ available as python3 or python3.11
#   - systemd-based Linux distribution
#   - Root / sudo privileges

set -euo pipefail

INSTALL_DIR="${1:-/opt/telegram-agent}"
SERVICE_NAME="telegram-agent"
SERVICE_USER="telegram-agent"
ENV_DIR="/etc/telegram-agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------- helpers ----------

info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[1;32m[OK]\033[0m    %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*"; exit 1; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (try: sudo $0)"
    fi
}

find_python() {
    for candidate in python3.11 python3; do
        if command -v "$candidate" &>/dev/null; then
            local ver
            ver="$("$candidate" --version 2>&1 | awk '{print $2}')"
            local major minor
            major="${ver%%.*}"
            minor="${ver#*.}"; minor="${minor%%.*}"
            if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
                echo "$candidate"
                return
            fi
        fi
    done
    error "Python 3.11+ is required but not found. Install it first."
}

# ---------- main ----------

require_root

PYTHON_BIN="$(find_python)"
info "Using Python: $PYTHON_BIN ($(${PYTHON_BIN} --version 2>&1))"

# 1. Create system user (no login shell, no home directory)
if id "$SERVICE_USER" &>/dev/null; then
    info "User '$SERVICE_USER' already exists"
else
    info "Creating system user '$SERVICE_USER'..."
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    ok "User '$SERVICE_USER' created"
fi

# 2. Copy project to INSTALL_DIR (skip if we are already there)
if [[ "$(realpath "$PROJECT_ROOT")" != "$(realpath "$INSTALL_DIR")" ]]; then
    info "Copying project to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    rsync -a --exclude='.venv' --exclude='venv' --exclude='.git' \
        --exclude='__pycache__' --exclude='*.pyc' \
        "$PROJECT_ROOT/" "$INSTALL_DIR/"
    ok "Project copied to $INSTALL_DIR"
else
    info "Project is already at $INSTALL_DIR -- skipping copy"
fi

# 3. Create virtual environment and install dependencies
info "Setting up Python virtual environment..."
"$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip --quiet
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
ok "Dependencies installed"

# Create runtime directories
mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"

# Set ownership
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"
ok "Ownership set to $SERVICE_USER"

# 4. Create environment directory
mkdir -p "$ENV_DIR"
if [[ ! -f "$ENV_DIR/env" ]]; then
    if [[ -f "$PROJECT_ROOT/.env.example" ]]; then
        cp "$PROJECT_ROOT/.env.example" "$ENV_DIR/env"
        warn "Copied .env.example to $ENV_DIR/env -- edit it with your real secrets!"
    else
        cat > "$ENV_DIR/env" <<'ENVEOF'
# Telegram Agent environment variables
# Fill in your values and restart the service:
#   sudo systemctl restart telegram-agent

TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
ANTHROPIC_API_KEY=
ENVIRONMENT=production
LOG_LEVEL=INFO
ENVEOF
        warn "Created skeleton $ENV_DIR/env -- edit it with your real secrets!"
    fi
    chmod 600 "$ENV_DIR/env"
    chown root:root "$ENV_DIR/env"
else
    info "$ENV_DIR/env already exists -- not overwriting"
fi

# 5. Install systemd service
info "Installing systemd service..."
cp "$INSTALL_DIR/deploy/telegram-agent.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
ok "Service installed and enabled"

# 6. Start the service
info "Starting $SERVICE_NAME..."
systemctl start "$SERVICE_NAME"
sleep 2

# 7. Print status
echo ""
echo "========================================="
systemctl status "$SERVICE_NAME" --no-pager || true
echo "========================================="
echo ""
ok "Installation complete!"
echo ""
info "Useful commands:"
echo "  sudo systemctl status  $SERVICE_NAME   # Check status"
echo "  sudo systemctl restart $SERVICE_NAME   # Restart"
echo "  sudo systemctl stop    $SERVICE_NAME   # Stop"
echo "  sudo journalctl -u     $SERVICE_NAME   # View logs"
echo "  sudo vim $ENV_DIR/env                  # Edit environment"
echo ""
