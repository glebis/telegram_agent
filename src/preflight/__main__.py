#!/usr/bin/env python3
# src/preflight/__main__.py
"""
CLI for running preflight checks.

Usage:
    python -m src.preflight [--verbose] [--json] [--no-fix]

Options:
    --verbose   Show detailed output for each check
    --json      Output results as JSON
    --no-fix    Don't attempt to auto-fix issues
"""

import argparse
import json
import sys

from src.preflight import run_all_checks
from src.preflight.models import CheckStatus, PreflightReport


# ANSI color codes
COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "cyan": "\033[96m",
}

STATUS_COLORS = {
    CheckStatus.PASS: "green",
    CheckStatus.FAIL: "red",
    CheckStatus.WARNING: "yellow",
    CheckStatus.FIXED: "blue",
}

STATUS_ICONS = {
    CheckStatus.PASS: "✓",
    CheckStatus.FAIL: "✗",
    CheckStatus.WARNING: "⚠",
    CheckStatus.FIXED: "🔧",
}


def colorize(text: str, color: str) -> str:
    """Wrap text in ANSI color codes."""
    if not sys.stdout.isatty():
        return text
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def format_verbose_output(report: PreflightReport) -> str:
    """Format report for verbose human-readable output."""
    lines = []
    lines.append(colorize("\n═══ Preflight Checks ═══\n", "bold"))

    for check in report.checks:
        color = STATUS_COLORS.get(check.status, "reset")
        icon = STATUS_ICONS.get(check.status, "?")
        status_str = check.status.value.upper()

        # Check name and status
        lines.append(f"{colorize(icon, color)} {colorize(check.name, 'bold')}: {colorize(status_str, color)}")

        # Message
        lines.append(f"  {check.message}")

        # Details if present
        if check.details:
            lines.append(f"  {colorize('Details:', 'cyan')} {check.details}")

        # Fix applied indicator
        if check.fix_applied:
            lines.append(f"  {colorize('(auto-fixed)', 'blue')}")

        lines.append("")

    # Summary
    lines.append(colorize("═══ Summary ═══", "bold"))
    lines.append(f"  {colorize('Passed:', 'green')} {report.passed}")
    lines.append(f"  {colorize('Failed:', 'red')} {report.failed}")
    lines.append(f"  {colorize('Warnings:', 'yellow')} {report.warnings}")
    lines.append(f"  {colorize('Fixed:', 'blue')} {report.fixed}")
    lines.append("")

    if report.should_block_startup:
        lines.append(colorize("❌ Preflight FAILED - startup blocked", "red"))
    else:
        lines.append(colorize("✅ Preflight PASSED - ready to start", "green"))

    return "\n".join(lines)


def format_simple_output(report: PreflightReport) -> str:
    """Format report for simple output (non-verbose)."""
    lines = []

    # Only show failures and fixes
    for check in report.checks:
        if check.status == CheckStatus.FAIL:
            lines.append(f"FAIL: {check.name} - {check.message}")
        elif check.status == CheckStatus.FIXED:
            lines.append(f"FIXED: {check.name} - {check.message}")
        elif check.status == CheckStatus.WARNING:
            lines.append(f"WARN: {check.name} - {check.message}")

    if not lines:
        lines.append("All preflight checks passed")
    else:
        lines.append(f"\nTotal: {report.passed} passed, {report.failed} failed, {report.warnings} warnings, {report.fixed} fixed")

    if report.should_block_startup:
        lines.append("Preflight FAILED")
    else:
        lines.append("Preflight PASSED")

    return "\n".join(lines)


def main():
    """Run preflight checks and output results."""
    parser = argparse.ArgumentParser(
        description="Run preflight checks before starting the bot",
        prog="python -m src.preflight"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output for each check"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--no-fix",
        action="store_true",
        help="Don't attempt to auto-fix issues"
    )

    args = parser.parse_args()

    # Run checks
    auto_fix = not args.no_fix
    report = run_all_checks(auto_fix=auto_fix)

    # Output results
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    elif args.verbose:
        print(format_verbose_output(report))
    else:
        print(format_simple_output(report))

    # Exit with appropriate code
    sys.exit(report.get_exit_code())


if __name__ == "__main__":
    main()
