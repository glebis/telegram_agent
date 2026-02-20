#!/bin/bash
# Auto-run defaults.yaml validation tests when config files are edited.
# Claude Code PostToolUse hook.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only trigger for config YAML files and the config.py settings class
case "$FILE_PATH" in
  */config/defaults.yaml|*/config/settings.yaml|*/config/profiles/*.yaml|*/src/core/config.py|*/src/core/defaults_loader.py)
    ;;
  *)
    exit 0
    ;;
esac

cd /Users/server/ai_projects/telegram_agent

PYTHON_PATH="/opt/homebrew/bin/python3.11"
TEST_OUTPUT=$($PYTHON_PATH -m pytest tests/test_defaults_loader.py tests/test_core/test_config.py -v --tb=short 2>&1)
TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
  echo "Config validation tests passed after editing $FILE_PATH" >&2
  exit 0
else
  TRUNCATED=$(echo "$TEST_OUTPUT" | tail -40)
  echo "Config validation tests FAILED after editing $FILE_PATH:" >&2
  echo "$TRUNCATED" >&2
  exit 2
fi
