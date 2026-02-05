"""
Utility module for checking availability of external CLI tools and Python packages.

Provides graceful detection so callers can fail with clear error messages
instead of crashing when a required tool is missing.

Usage:
    from src.utils.tool_check import check_tool, check_python_package, get_missing_tools

    if not check_tool("marker_single"):
        hint = format_install_hint("marker_single")
        raise RuntimeError(f"marker_single is not installed. {hint}")

    missing = get_missing_tools(["curl", "marker_single"])
    if missing:
        hints = [format_install_hint(t) for t in missing]
        ...
"""

import importlib
import logging
import platform
import shutil
from typing import Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool -> install hint mapping
# Keyed by tool name, values are dicts of platform -> install command.
# "darwin" = macOS (Homebrew), "linux" = Linux (apt), "pip" = Python package.
# ---------------------------------------------------------------------------
_INSTALL_HINTS: Dict[str, Dict[str, str]] = {
    "marker_single": {
        "darwin": "pip install marker-pdf",
        "linux": "pip install marker-pdf",
        "pip": "pip install marker-pdf",
    },
    "curl": {
        "darwin": "brew install curl",
        "linux": "sudo apt-get install curl",
    },
    "psutil": {
        "darwin": "pip install psutil",
        "linux": "pip install psutil",
        "pip": "pip install psutil",
    },
    "pyngrok": {
        "darwin": "pip install pyngrok",
        "linux": "pip install pyngrok",
        "pip": "pip install pyngrok",
    },
    "ngrok": {
        "darwin": "brew install ngrok/ngrok/ngrok",
        "linux": "snap install ngrok  # or see https://ngrok.com/download",
    },
    "ffmpeg": {
        "darwin": "brew install ffmpeg",
        "linux": "sudo apt-get install ffmpeg",
    },
    "sqlite3": {
        "darwin": "brew install sqlite",
        "linux": "sudo apt-get install sqlite3",
    },
}

# ---------------------------------------------------------------------------
# Job type -> required CLI tools mapping
# Used by worker_queue.py to pre-check tools before executing a job.
# ---------------------------------------------------------------------------
JOB_TOOL_REQUIREMENTS: Dict[str, List[str]] = {
    "pdf_convert": ["marker_single", "curl"],
    "pdf_save": ["marker_single", "curl"],
}


def check_tool(name: str) -> bool:
    """Check if a CLI tool is available on the system PATH.

    Args:
        name: The executable name to look up (e.g. "curl", "marker_single").

    Returns:
        True if the tool is found on PATH, False otherwise.
    """
    found = shutil.which(name) is not None
    if not found:
        logger.debug("CLI tool %r not found on PATH", name)
    return found


def check_python_package(name: str) -> bool:
    """Check if a Python package is importable.

    Args:
        name: The top-level package name (e.g. "psutil", "pyngrok").

    Returns:
        True if the package can be imported, False otherwise.
    """
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        logger.debug("Python package %r is not importable", name)
        return False


def get_missing_tools(required: List[str]) -> List[str]:
    """Return the subset of *required* CLI tools that are not available.

    Args:
        required: List of executable names to check.

    Returns:
        List of tool names that are missing (empty list if all present).
    """
    return [t for t in required if not check_tool(t)]


def get_missing_python_packages(required: List[str]) -> List[str]:
    """Return the subset of *required* Python packages that are not importable.

    Args:
        required: List of package names to check.

    Returns:
        List of package names that are missing (empty list if all present).
    """
    return [p for p in required if not check_python_package(p)]


def _get_platform_key() -> str:
    """Return a platform key for install hints.

    Returns:
        'darwin' for macOS, 'linux' for Linux/WSL, 'windows' for Windows.
    """
    system = platform.system().lower()
    if system == "darwin":
        return "darwin"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    return "linux"  # fallback to Linux hints


def format_install_hint(tool: str) -> str:
    """Return a platform-appropriate install hint for the given tool.

    On macOS, suggests Homebrew commands.  On Linux/WSL, suggests apt-get.
    Falls back to a generic message if the tool is not in the hints database.

    Args:
        tool: The tool or package name.

    Returns:
        A human-readable install instruction string.
    """
    plat = _get_platform_key()
    hints = _INSTALL_HINTS.get(tool, {})

    if plat in hints:
        return f"Install with: {hints[plat]}"

    # Try pip hint as fallback
    if "pip" in hints:
        return f"Install with: {hints['pip']}"

    # Generic fallback
    if plat == "darwin":
        return f"Install '{tool}' via Homebrew or pip (macOS)"
    elif plat == "linux":
        return f"Install '{tool}' via apt-get or pip (Linux)"
    else:
        return f"Install '{tool}' for your platform"


def format_missing_tools_error(missing: List[str]) -> str:
    """Format a user-friendly error message listing all missing tools with install hints.

    Args:
        missing: List of missing tool names.

    Returns:
        Multi-line error string ready for logging or user display.
    """
    if not missing:
        return ""

    lines = [f"Missing required tool(s): {', '.join(missing)}"]
    for tool in missing:
        hint = format_install_hint(tool)
        lines.append(f"  - {tool}: {hint}")
    return "\n".join(lines)
