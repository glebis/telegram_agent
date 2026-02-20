#!/bin/bash
# Auto-run contact path traversal tests when message_handlers.py is edited.
# Claude Code PostToolUse hook.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only trigger for files related to contact handling / path traversal
case "$FILE_PATH" in
  */message_handlers.py|*/test_message_handlers.py|*/test_contact_research_callback.py)
    ;;
  *)
    exit 0
    ;;
esac

cd /Users/server/ai_projects/telegram_agent

PYTHON_PATH="/opt/homebrew/bin/python3.11"
TEST_OUTPUT=$($PYTHON_PATH -m pytest tests/test_bot/test_message_handlers.py::TestContactPathTraversal tests/test_bot/test_contact_research_callback.py -v --tb=short 2>&1)
TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
  echo "Contact handler tests passed after editing $FILE_PATH" >&2
  exit 0
else
  TRUNCATED=$(echo "$TEST_OUTPUT" | tail -40)
  echo "Contact handler tests FAILED after editing $FILE_PATH:" >&2
  echo "$TRUNCATED" >&2
  exit 2
fi
