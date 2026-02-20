#!/bin/bash
# Auto-format Python files after Edit/Write with black + isort.
# Claude Code PostToolUse hook.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only trigger for .py files under src/ or tests/
case "$FILE_PATH" in
  */src/*.py|*/tests/*.py)
    ;;
  *)
    exit 0
    ;;
esac

# Skip if file doesn't exist (e.g. deleted)
[ -f "$FILE_PATH" ] || exit 0

PYTHON_PATH="/opt/homebrew/bin/python3.11"

$PYTHON_PATH -m black --quiet "$FILE_PATH" 2>/dev/null || true
$PYTHON_PATH -m isort --quiet "$FILE_PATH" 2>/dev/null || true
