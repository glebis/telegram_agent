# src/preflight/__init__.py
"""
Preflight check system for Verity.

Validates environment, dependencies, and configuration before startup.
Auto-fixes known issues when possible.
"""

from src.preflight.checks import (
    check_config_files,
    check_database,
    check_dependencies,
    check_directory_structure,
    check_environment_variables,
    check_optional_tools,
    check_port_availability,
    check_python_version,
)
from src.preflight.fixes import fix_missing_dependencies, fix_port_conflict
from src.preflight.models import CheckResult, CheckStatus, FixResult, PreflightReport

__all__ = [
    # Models
    "CheckStatus",
    "CheckResult",
    "PreflightReport",
    "FixResult",
    # Checks
    "check_python_version",
    "check_dependencies",
    "check_optional_tools",
    "check_environment_variables",
    "check_port_availability",
    "check_directory_structure",
    "check_database",
    "check_config_files",
    # Fixes
    "fix_missing_dependencies",
    "fix_port_conflict",
    # Runner
    "run_all_checks",
]


def run_all_checks(auto_fix: bool = True) -> PreflightReport:
    """
    Run all preflight checks and return a report.

    Args:
        auto_fix: If True, attempt to automatically fix issues.

    Returns:
        PreflightReport with results of all checks.
    """
    # Define checks with their names for better error reporting
    checks = [
        ("python_version", check_python_version),
        ("dependencies", lambda: check_dependencies(auto_fix=auto_fix)),
        ("optional_tools", check_optional_tools),
        ("environment_variables", check_environment_variables),
        ("port_availability", lambda: check_port_availability(auto_fix=auto_fix)),
        ("directory_structure", lambda: check_directory_structure(auto_fix=auto_fix)),
        ("database", check_database),
        ("config_files", check_config_files),
    ]

    results = []
    for name, check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            # If a check itself fails, record it as a failure
            results.append(
                CheckResult(
                    name=name,
                    status=CheckStatus.FAIL,
                    message=f"Check raised exception: {type(e).__name__}",
                    details=str(e),
                )
            )

    return PreflightReport(checks=results)
