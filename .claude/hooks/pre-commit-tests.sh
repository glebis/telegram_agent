#!/bin/bash
# Run test suite on files touched by the current commit before committing.
# Claude Code PreToolUse hook — triggers on "Bash" when the command is "git commit".

set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only trigger for git commit commands
case "$COMMAND" in
  git\ commit*) ;;
  *) exit 0 ;;
esac

cd /Users/server/ai_projects/telegram_agent
PYTHON_PATH="/opt/homebrew/bin/python3.11"

# 1. Run flake8 (fast lint check)
FLAKE_OUTPUT=$($PYTHON_PATH -m flake8 src/ tests/ 2>&1)
FLAKE_EXIT_CODE=$?

if [ $FLAKE_EXIT_CODE -ne 0 ]; then
  echo "Pre-commit flake8 FAILED — fix before committing:" >&2
  echo "$FLAKE_OUTPUT" >&2
  exit 2
fi
echo "Pre-commit flake8 passed" >&2

# 2. Run black --check (catch formatting drift not caught by auto-format hook)
BLACK_OUTPUT=$($PYTHON_PATH -m black --check --quiet src/ tests/ 2>&1)
BLACK_EXIT_CODE=$?

if [ $BLACK_EXIT_CODE -ne 0 ]; then
  echo "Pre-commit black --check FAILED — run 'python -m black src/ tests/' to fix:" >&2
  echo "$BLACK_OUTPUT" >&2
  exit 2
fi
echo "Pre-commit black passed" >&2

# 3. Run isort --check (import order — matches CI)
ISORT_OUTPUT=$($PYTHON_PATH -m isort --check --quiet src/ tests/ 2>&1)
ISORT_EXIT_CODE=$?

if [ $ISORT_EXIT_CODE -ne 0 ]; then
  echo "Pre-commit isort FAILED — run 'python -m isort src/ tests/' to fix:" >&2
  echo "$ISORT_OUTPUT" >&2
  exit 2
fi
echo "Pre-commit isort passed" >&2

# 4. Run mypy (type check — catches errors CI would catch)
MYPY_OUTPUT=$($PYTHON_PATH -m mypy src/ 2>&1)
MYPY_EXIT_CODE=$?

if [ $MYPY_EXIT_CODE -ne 0 ]; then
  TRUNCATED=$(echo "$MYPY_OUTPUT" | tail -30)
  echo "Pre-commit mypy FAILED — fix type errors before committing:" >&2
  echo "$TRUNCATED" >&2
  exit 2
fi
echo "Pre-commit mypy passed" >&2

# 5. Run the test suite (excluding test_api, matching CI config)
TEST_OUTPUT=$($PYTHON_PATH -m pytest tests/ --ignore=tests/test_api -q --tb=line 2>&1)
TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
  echo "Pre-commit tests passed" >&2
  exit 0
else
  TRUNCATED=$(echo "$TEST_OUTPUT" | tail -30)
  echo "Pre-commit tests FAILED — fix before committing:" >&2
  echo "$TRUNCATED" >&2
  exit 2
fi
