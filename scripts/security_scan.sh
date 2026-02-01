#!/bin/bash
# Security scanning script for telegram_agent
# Runs: bandit, pip-audit, safety, and security tests

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "============================================"
echo "  Security Scan: telegram_agent"
echo "============================================"
echo ""

# 1. Bandit - Static analysis for security issues
echo "[1/4] Running bandit (static security analysis)..."
echo "--------------------------------------------"
python -m bandit -r src/ -c pyproject.toml --format text 2>&1 || true
echo ""

# 2. pip-audit - Check for known vulnerabilities in dependencies
echo "[2/4] Running pip-audit (dependency vulnerabilities)..."
echo "--------------------------------------------"
python -m pip_audit 2>&1 || true
echo ""

# 3. Safety - Check dependencies against safety DB
echo "[3/4] Running safety check..."
echo "--------------------------------------------"
python -m safety check 2>&1 || true
echo ""

# 4. Security test suite
echo "[4/4] Running security tests..."
echo "--------------------------------------------"
python -m pytest tests/test_security/ -v --no-header 2>&1 || true
echo ""

echo "============================================"
echo "  Security Scan Complete"
echo "============================================"
