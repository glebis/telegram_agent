#!/usr/bin/env bash
# Remove all telegram-agent launchd services.
#
# Usage:
#   scripts/uninstall_launchd.sh              # remove all services
#   scripts/uninstall_launchd.sh --dry-run    # show what would be removed
set -euo pipefail

GUI_DOMAIN="gui/$(id -u)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=true
fi

# Find all telegram-agent plists (both hyphen and underscore variants)
PLISTS=()
for plist in "$LAUNCH_AGENTS"/com.telegram-agent.*.plist "$LAUNCH_AGENTS"/com.telegram_agent.*.plist; do
    [ -f "$plist" ] && PLISTS+=("$plist")
done

if [ ${#PLISTS[@]} -eq 0 ]; then
    echo "No telegram-agent services found in $LAUNCH_AGENTS"
    exit 0
fi

removed=0
for plist in "${PLISTS[@]}"; do
    filename="$(basename "$plist")"
    # Extract label from filename (strip .plist extension)
    label="${filename%.plist}"

    if $DRY_RUN; then
        echo "Would remove: $label ($plist)"
    else
        launchctl bootout "$GUI_DOMAIN/$label" 2>/dev/null || true
        rm -f "$plist"
        echo "  OK  removed $label"
        removed=$((removed + 1))
    fi
done

if $DRY_RUN; then
    echo ""
    echo "Dry run complete. ${#PLISTS[@]} service(s) would be removed."
else
    echo ""
    echo "Removed $removed service(s)."
fi
