"""
Subprocess Sandbox

Provides a wrapper for running external commands (ffmpeg, imagemagick, etc.)
with enforced timeouts, resource limits, and output capping.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SubprocessResult:
    """Structured result from a sandboxed subprocess execution."""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool = False
    error: Optional[str] = None


def run_sandboxed(
    cmd: List[str],
    timeout_seconds: int = 30,
    max_output_bytes: int = 50_000_000,
    cwd: Optional[str] = None,
) -> SubprocessResult:
    """
    Run an external command with timeout and output-size limits.

    Args:
        cmd: Command and arguments as a list (e.g. ``["ffmpeg", "-i", ...]``).
        timeout_seconds: Maximum wall-clock time before the process is killed.
        max_output_bytes: Maximum bytes to retain from stdout/stderr.
            Output beyond this limit is truncated.
        cwd: Optional working directory.

    Returns:
        ``SubprocessResult`` with captured output and status.
    """
    if not cmd:
        return SubprocessResult(
            success=False,
            stdout="",
            stderr="",
            return_code=-1,
            timed_out=False,
            error="Empty command list",
        )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=cwd,
        )

        stdout = result.stdout[:max_output_bytes].decode("utf-8", errors="replace")
        stderr = result.stderr[:max_output_bytes].decode("utf-8", errors="replace")

        return SubprocessResult(
            success=result.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            return_code=result.returncode,
            timed_out=False,
            error=(
                None
                if result.returncode == 0
                else f"Process exited with code {result.returncode}"
            ),
        )

    except subprocess.TimeoutExpired as exc:
        logger.warning(
            "Sandboxed process timed out after %ds: %s", timeout_seconds, cmd
        )
        stdout = ""
        stderr = ""
        if exc.stdout:
            stdout = exc.stdout[:max_output_bytes].decode("utf-8", errors="replace")
        if exc.stderr:
            stderr = exc.stderr[:max_output_bytes].decode("utf-8", errors="replace")

        return SubprocessResult(
            success=False,
            stdout=stdout,
            stderr=stderr,
            return_code=-1,
            timed_out=True,
            error=f"Timeout after {timeout_seconds} seconds",
        )

    except FileNotFoundError:
        logger.error("Command not found: %s", cmd[0] if cmd else "<empty>")
        return SubprocessResult(
            success=False,
            stdout="",
            stderr=f"Command not found: {cmd[0]}",
            return_code=-1,
            timed_out=False,
            error=f"Command not found: {cmd[0]}",
        )

    except Exception as exc:
        logger.error("Sandboxed subprocess error: %s", exc, exc_info=True)
        return SubprocessResult(
            success=False,
            stdout="",
            stderr=str(exc),
            return_code=-1,
            timed_out=False,
            error=str(exc),
        )
