#!/usr/bin/env bash
# Install launchd services from templatized plist files.
#
# Usage:
#   scripts/install_launchd.sh                  # install all services
#   scripts/install_launchd.sh bot health       # install only named services
#   scripts/install_launchd.sh --dry-run        # show what would be installed
#   scripts/install_launchd.sh --dry-run bot    # dry-run for a single service
set -euo pipefail

# ── Resolve paths ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE_DIR="$PROJECT_ROOT/ops/launchd"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
GUI_DOMAIN="gui/$(id -u)"

# ── Detect Python ──────────────────────────────────────────────────
if [ -n "${PYTHON_BIN:-}" ]; then
    :  # use env var
elif [ -x /opt/homebrew/bin/python3.11 ]; then
    PYTHON_BIN=/opt/homebrew/bin/python3.11
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "ERROR: No Python found. Set PYTHON_BIN or install python3." >&2
    exit 1
fi

# ── Parse arguments ────────────────────────────────────────────────
DRY_RUN=false
SERVICES=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [service-name...]"
            echo ""
            echo "  No args      install all services"
            echo "  service-name install only matching services (substring match)"
            echo "  --dry-run    show substitutions without installing"
            exit 0
            ;;
        *) SERVICES+=("$arg") ;;
    esac
done

# ── Collect plist templates ────────────────────────────────────────
PLISTS=()
for plist in "$TEMPLATE_DIR"/*.plist; do
    [ -f "$plist" ] || continue
    filename="$(basename "$plist")"

    # Filter by service name if arguments given
    if [ ${#SERVICES[@]} -gt 0 ]; then
        matched=false
        for svc in "${SERVICES[@]}"; do
            if [[ "$filename" == *"$svc"* ]]; then
                matched=true
                break
            fi
        done
        "$matched" || continue
    fi

    PLISTS+=("$plist")
done

if [ ${#PLISTS[@]} -eq 0 ]; then
    echo "No matching plist templates found in $TEMPLATE_DIR"
    exit 1
fi

# ── Ensure directories exist ──────────────────────────────────────
if ! $DRY_RUN; then
    mkdir -p "$LAUNCH_AGENTS"
    mkdir -p "$PROJECT_ROOT/logs"
fi

echo "Project root : $PROJECT_ROOT"
echo "Python binary: $PYTHON_BIN"
echo "Home         : $HOME"
echo "Mode         : $($DRY_RUN && echo 'DRY RUN' || echo 'INSTALL')"
echo ""

# ── Install each plist ─────────────────────────────────────────────
installed=0
failed=0
for plist in "${PLISTS[@]}"; do
    filename="$(basename "$plist")"

    # Substitute placeholders
    content="$(sed \
        -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
        -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" \
        -e "s|__HOME__|$HOME|g" \
        "$plist")"

    # Extract label (Label key and string value are on separate lines)
    label="$(echo "$content" | grep -A1 '<key>Label</key>' | grep '<string>' | sed 's/.*<string>\(.*\)<\/string>.*/\1/' | head -1)"
    if [ -z "$label" ]; then
        echo "WARN: Could not extract label from $filename, skipping"
        continue
    fi

    # Check for leftover placeholders
    if echo "$content" | grep -q '__[A-Z_]*__'; then
        echo "ERROR: Unresolved placeholders in $filename:"
        echo "$content" | grep '__[A-Z_]*__'
        exit 1
    fi

    dest="$LAUNCH_AGENTS/$filename"

    if $DRY_RUN; then
        echo "[$label]"
        echo "  template: $plist"
        echo "  dest:     $dest"
        echo ""
    else
        # Bootout existing service (ignore errors)
        launchctl bootout "$GUI_DOMAIN/$label" 2>/dev/null || true

        # Write substituted plist
        echo "$content" > "$dest"

        # Bootstrap service
        if launchctl bootstrap "$GUI_DOMAIN" "$dest" 2>/dev/null; then
            echo "  OK  $label"
            installed=$((installed + 1))
        else
            echo "  WARN  $label — bootstrap failed, retrying with kickstart..."
            # Force-start for KeepAlive services that resist bootout/bootstrap
            if launchctl kickstart -k "$GUI_DOMAIN/$label" 2>/dev/null; then
                echo "  OK  $label (kickstarted)"
                installed=$((installed + 1))
            else
                echo "  FAIL  $label — load manually: launchctl bootstrap $GUI_DOMAIN $dest"
                failed=$((failed + 1))
            fi
        fi
    fi
done

if $DRY_RUN; then
    echo "Dry run complete. ${#PLISTS[@]} service(s) would be installed."
else
    echo ""
    echo "Installed $installed service(s)."
    if [ "$failed" -gt 0 ]; then
        echo "$failed service(s) failed — see WARN/FAIL messages above."
        exit 1
    fi
fi
