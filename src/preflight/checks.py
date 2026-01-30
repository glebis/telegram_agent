# src/preflight/checks.py
"""Preflight check functions."""

import importlib
import os
import socket
import sys
from pathlib import Path

import psutil

from src.preflight.models import CheckStatus, CheckResult
from src.preflight.fixes import fix_missing_dependencies, fix_port_conflict


# Critical modules that must be importable
CRITICAL_MODULES = [
    "fastapi",
    "uvicorn",
    "telegram",
    "telegram.ext",
    "sqlalchemy",
    "aiosqlite",
    "litellm",
    "openai",
    "frontmatter",
    "structlog",
    "rich",
    "pydantic",
    "httpx",
]

# Environment variables
REQUIRED_ENV_VARS = ["TELEGRAM_BOT_TOKEN"]
OPTIONAL_ENV_VARS = ["GROQ_API_KEY", "OBSIDIAN_VAULT_PATH"]

# Port configuration
DEFAULT_PORT = 8847

# Directory structure
PROJECT_ROOT = Path(__file__).parent.parent.parent
REQUIRED_DIRS = [
    str(PROJECT_ROOT / "data"),
    str(PROJECT_ROOT / "data" / "raw"),
    str(PROJECT_ROOT / "data" / "img"),
    str(PROJECT_ROOT / "logs"),
]

# Database path
DATABASE_PATH = str(PROJECT_ROOT / "data" / "telegram_agent.db")

# Config files
REQUIRED_CONFIGS = [
    str(PROJECT_ROOT / "config" / "modes.yaml"),
    str(PROJECT_ROOT / "config" / "settings.yaml"),
]


def check_python_version() -> CheckResult:
    """
    Check Python version is 3.11+.

    Returns:
        CheckResult with PASS for 3.11, WARNING for >3.11, FAIL for <3.11.
    """
    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}.{sys.version_info[2]}"

    if major < 3 or (major == 3 and minor < 11):
        return CheckResult(
            name="python_version",
            status=CheckStatus.FAIL,
            message=f"Python 3.11+ required, found {version_str}",
            details="Upgrade Python to 3.11 or later"
        )
    elif major == 3 and minor == 11:
        return CheckResult(
            name="python_version",
            status=CheckStatus.PASS,
            message=f"Python {version_str}",
            details="Python version OK"
        )
    else:
        # Python 3.12+ is untested
        return CheckResult(
            name="python_version",
            status=CheckStatus.WARNING,
            message=f"Python {version_str} is untested (3.11 recommended)",
            details="May work but not officially supported"
        )


def check_dependencies(auto_fix: bool = True) -> CheckResult:
    """
    Check all required dependencies are importable.

    Args:
        auto_fix: If True, attempt to install missing dependencies.

    Returns:
        CheckResult with status based on import success.
    """
    missing = []

    for module_name in CRITICAL_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)

    if not missing:
        return CheckResult(
            name="dependencies",
            status=CheckStatus.PASS,
            message="All dependencies available",
            details=f"Checked {len(CRITICAL_MODULES)} modules"
        )

    if not auto_fix:
        return CheckResult(
            name="dependencies",
            status=CheckStatus.FAIL,
            message=f"Missing dependencies: {', '.join(missing)}",
            details="Run 'pip install -r requirements.txt' to fix"
        )

    # Attempt auto-fix
    fix_result = fix_missing_dependencies(missing)

    if fix_result.success:
        # Verify the fix worked
        still_missing = []
        for module_name in missing:
            try:
                # Force reimport
                if module_name in sys.modules:
                    del sys.modules[module_name]
                importlib.import_module(module_name)
            except ImportError:
                still_missing.append(module_name)

        if not still_missing:
            return CheckResult(
                name="dependencies",
                status=CheckStatus.FIXED,
                message=f"Installed missing dependencies: {', '.join(missing)}",
                details=fix_result.details,
                fix_applied=True
            )
        else:
            return CheckResult(
                name="dependencies",
                status=CheckStatus.FAIL,
                message=f"Still missing after fix: {', '.join(still_missing)}",
                details="pip install succeeded but imports still fail"
            )
    else:
        return CheckResult(
            name="dependencies",
            status=CheckStatus.FAIL,
            message=f"Missing dependencies: {', '.join(missing)}",
            details=fix_result.details
        )


def check_environment_variables() -> CheckResult:
    """
    Check required environment variables are set.

    Returns:
        CheckResult with FAIL if critical vars missing, WARNING if optional missing.
    """
    missing_required = []
    missing_optional = []

    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            missing_required.append(var)

    for var in OPTIONAL_ENV_VARS:
        if not os.environ.get(var):
            missing_optional.append(var)

    if missing_required:
        return CheckResult(
            name="environment_variables",
            status=CheckStatus.FAIL,
            message=f"Missing required env vars: {', '.join(missing_required)}",
            details="Set these in .env or .env.local"
        )

    if missing_optional:
        return CheckResult(
            name="environment_variables",
            status=CheckStatus.WARNING,
            message=f"Missing optional env vars: {', '.join(missing_optional)}",
            details="Some features may be disabled"
        )

    return CheckResult(
        name="environment_variables",
        status=CheckStatus.PASS,
        message="All environment variables set",
        details=f"Required: {REQUIRED_ENV_VARS}, Optional: {OPTIONAL_ENV_VARS}"
    )


def _find_process_on_port(port: int) -> int | None:
    """Find PID of process using the given port."""
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                return conn.pid
    except psutil.AccessDenied:
        # On macOS, this may require elevated permissions
        # Fall back to using lsof via subprocess
        import subprocess
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # Return first PID found
                return int(result.stdout.strip().split()[0])
        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
            pass
    return None


def check_port_availability(auto_fix: bool = True, port: int = DEFAULT_PORT) -> CheckResult:
    """
    Check the configured port is available.

    Args:
        auto_fix: If True, attempt to kill stale processes.
        port: Port number to check.

    Returns:
        CheckResult with status based on port availability.
    """
    def try_bind(port: int) -> bool:
        """Attempt to bind to the port."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("0.0.0.0", port))
                return True
        except OSError:
            return False

    if try_bind(port):
        return CheckResult(
            name="port_availability",
            status=CheckStatus.PASS,
            message=f"Port {port} is available",
            details=None
        )

    # Port is in use
    pid = _find_process_on_port(port)

    if not auto_fix:
        return CheckResult(
            name="port_availability",
            status=CheckStatus.FAIL,
            message=f"Port {port} is in use" + (f" by PID {pid}" if pid else ""),
            details="Stop the process or use a different port"
        )

    if pid is None:
        return CheckResult(
            name="port_availability",
            status=CheckStatus.FAIL,
            message=f"Port {port} is in use but could not find process",
            details="Manually free the port"
        )

    # Attempt to fix
    fix_result = fix_port_conflict(port, pid)

    if fix_result.success:
        # Give the process time to release the port
        import time
        time.sleep(0.5)

        if try_bind(port):
            return CheckResult(
                name="port_availability",
                status=CheckStatus.FIXED,
                message=f"Killed stale process on port {port}",
                details=fix_result.details,
                fix_applied=True
            )

    return CheckResult(
        name="port_availability",
        status=CheckStatus.FAIL,
        message=f"Port {port} is in use and could not be freed",
        details=fix_result.details if fix_result else "Unknown error"
    )


def check_directory_structure(auto_fix: bool = True) -> CheckResult:
    """
    Check required directories exist.

    Args:
        auto_fix: If True, create missing directories.

    Returns:
        CheckResult with status based on directory existence.
    """
    missing = []
    created = []

    for dir_path in REQUIRED_DIRS:
        path = Path(dir_path)
        if not path.exists():
            if auto_fix:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    created.append(dir_path)
                except Exception as e:
                    missing.append(f"{dir_path} (error: {e})")
            else:
                missing.append(dir_path)

    if missing:
        return CheckResult(
            name="directory_structure",
            status=CheckStatus.FAIL,
            message=f"Missing directories: {', '.join(missing)}",
            details="Create these directories manually"
        )

    if created:
        return CheckResult(
            name="directory_structure",
            status=CheckStatus.FIXED,
            message=f"Created directories: {', '.join(created)}",
            details=None,
            fix_applied=True
        )

    return CheckResult(
        name="directory_structure",
        status=CheckStatus.PASS,
        message="All required directories exist",
        details=f"Checked: {', '.join(REQUIRED_DIRS)}"
    )


def check_database() -> CheckResult:
    """
    Check database file is accessible.

    Returns:
        CheckResult with status based on database state.
    """
    db_path = Path(DATABASE_PATH)

    if not db_path.exists():
        return CheckResult(
            name="database",
            status=CheckStatus.WARNING,
            message="Database not found (first run?)",
            details=f"Expected at {DATABASE_PATH}"
        )

    # Check if it's readable and looks like SQLite
    try:
        with open(db_path, "rb") as f:
            header = f.read(16)

        if not header.startswith(b"SQLite format 3"):
            return CheckResult(
                name="database",
                status=CheckStatus.FAIL,
                message="Database file is corrupt or invalid",
                details="File exists but is not a valid SQLite database"
            )

        return CheckResult(
            name="database",
            status=CheckStatus.PASS,
            message="Database OK",
            details=f"SQLite database at {DATABASE_PATH}"
        )

    except PermissionError:
        return CheckResult(
            name="database",
            status=CheckStatus.FAIL,
            message="Database file not readable",
            details=f"Permission denied for {DATABASE_PATH}"
        )
    except Exception as e:
        return CheckResult(
            name="database",
            status=CheckStatus.FAIL,
            message=f"Database check error: {type(e).__name__}",
            details=str(e)
        )


def check_config_files() -> CheckResult:
    """
    Check required config files exist.

    Returns:
        CheckResult with WARNING if missing (not critical).
    """
    missing = []

    for config_path in REQUIRED_CONFIGS:
        if not Path(config_path).exists():
            missing.append(Path(config_path).name)

    if missing:
        return CheckResult(
            name="config_files",
            status=CheckStatus.WARNING,
            message=f"Missing config files: {', '.join(missing)}",
            details="Some features may use defaults"
        )

    return CheckResult(
        name="config_files",
        status=CheckStatus.PASS,
        message="All config files present",
        details=f"Checked: {', '.join(Path(c).name for c in REQUIRED_CONFIGS)}"
    )
