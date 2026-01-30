# src/preflight/fixes.py
"""Auto-fix functions for preflight issues."""

import os
import signal
import subprocess
import sys
from pathlib import Path

import psutil

from src.preflight.models import FixResult


# Processes we're allowed to kill when they occupy our port
KILLABLE_PROCESS_PATTERNS = [
    "uvicorn",
    "python",
    "python3",
    "python3.11",
]


def fix_missing_dependencies(missing: list[str]) -> FixResult:
    """
    Attempt to install missing dependencies by running pip install.

    Args:
        missing: List of missing package names (for logging only).
                 We install from requirements.txt, not individual packages.

    Returns:
        FixResult indicating success or failure.
    """
    if not missing:
        return FixResult(
            success=True,
            message="Nothing to install",
            details="No missing dependencies"
        )

    # Find requirements.txt
    project_root = Path(__file__).parent.parent.parent
    requirements_file = project_root / "requirements.txt"

    if not requirements_file.exists():
        return FixResult(
            success=False,
            message="Failed to install dependencies",
            details=f"requirements.txt not found at {requirements_file}"
        )

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0:
            return FixResult(
                success=True,
                message="Dependencies installed successfully",
                details=f"Attempted to fix: {', '.join(missing)}"
            )
        else:
            return FixResult(
                success=False,
                message="Failed to install dependencies",
                details=f"pip returned code {result.returncode}: {result.stderr[:500]}"
            )

    except subprocess.TimeoutExpired:
        return FixResult(
            success=False,
            message="Timeout installing dependencies",
            details="pip install timed out after 5 minutes"
        )
    except Exception as e:
        return FixResult(
            success=False,
            message="Failed to install dependencies",
            details=str(e)
        )


def fix_port_conflict(port: int, pid: int) -> FixResult:
    """
    Attempt to kill process occupying the given port.

    Only kills processes that match known patterns (uvicorn, python).
    Will not kill unknown processes like nginx, postgres, etc.

    Args:
        port: The port number being checked.
        pid: The PID of the process to kill.

    Returns:
        FixResult indicating success or failure.
    """
    try:
        proc = psutil.Process(pid)
        proc_name = proc.name().lower()
        cmdline = proc.cmdline()
        cmdline_str = " ".join(cmdline).lower()

        # Check if this is a process we're allowed to kill
        is_killable = any(
            pattern in proc_name or pattern in cmdline_str
            for pattern in KILLABLE_PROCESS_PATTERNS
        )

        if not is_killable:
            return FixResult(
                success=False,
                message=f"Cannot kill unknown process type",
                details=f"Process {pid} ({proc_name}) is not a known process type we can safely kill"
            )

        # Kill the process
        os.kill(pid, signal.SIGTERM)

        return FixResult(
            success=True,
            message=f"Killed stale process on port {port}",
            details=f"Killed PID {pid}: {cmdline_str[:100]}"
        )

    except psutil.NoSuchProcess:
        return FixResult(
            success=True,
            message=f"Process no longer running",
            details=f"PID {pid} already exited, port {port} should be free"
        )
    except PermissionError as e:
        return FixResult(
            success=False,
            message="Permission denied killing process",
            details=f"Could not kill PID {pid}: {e}"
        )
    except Exception as e:
        return FixResult(
            success=False,
            message="Failed to kill process",
            details=f"Error killing PID {pid}: {e}"
        )
