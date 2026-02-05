"""Run OpenCode CLI in a subprocess to avoid event loop blocking issues.

Mirrors the pattern from claude_subprocess.py but wraps the OpenCode CLI
(https://github.com/opencode-ai/opencode) instead of the Claude Code SDK.

OpenCode is invoked via ``opencode run "prompt"`` for non-interactive mode.
"""

import logging
import os
import shutil
import subprocess
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Derive project root from this file's location
# (src/services/opencode_subprocess.py -> ../../)
_PROJECT_ROOT = str(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

# Timeout for OpenCode execution (5 minutes, matching Claude timeout)
OPENCODE_TIMEOUT_SECONDS = 300


def parse_opencode_output(raw_output: str) -> str:
    """Parse and clean raw output from the OpenCode CLI.

    Strips leading/trailing whitespace and normalizes the output for
    consumption by the service layer.

    Args:
        raw_output: The raw stdout string from the OpenCode subprocess.

    Returns:
        Cleaned output string.
    """
    if not raw_output:
        return ""
    return raw_output.strip()


def run_opencode_subprocess(
    prompt: str,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
    cwd: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Run OpenCode CLI in a subprocess and capture the result.

    Executes ``opencode run "prompt"`` with optional flags for model
    selection and session persistence.

    Args:
        prompt: The prompt to send to OpenCode.
        model: Optional model identifier (e.g. "anthropic:claude-sonnet-4-20250514",
            "openai:gpt-4o"). Passed as ``--model <model>``.
        session_id: Optional session ID for conversation persistence.
            Passed as ``--session <session_id>``.
        cwd: Optional working directory for the subprocess.
            Defaults to the project root.

    Returns:
        Dictionary with keys:
            - success (bool): Whether the command succeeded.
            - output (str): The stdout content on success, empty string on failure.
            - error (Optional[str]): Error message on failure, None on success.
            - session_id (Optional[str]): Session ID if returned by OpenCode.
    """
    # Check that opencode is installed
    opencode_bin = shutil.which("opencode")
    if opencode_bin is None:
        logger.error("OpenCode CLI is not installed or not found in PATH")
        return {
            "success": False,
            "output": "",
            "error": "OpenCode CLI is not installed or not found in PATH",
            "session_id": None,
        }

    # Build the command
    cmd = [opencode_bin, "run"]

    # Add optional flags
    if model is not None:
        cmd.extend(["--model", model])

    if session_id is not None:
        cmd.extend(["--session", session_id])

    # Add the prompt as the final argument
    cmd.append(prompt)

    # Default working directory
    if cwd is None:
        cwd = _PROJECT_ROOT

    logger.info(
        f"Running OpenCode subprocess: model={model}, session={session_id}, cwd={cwd}"
    )
    logger.debug(f"OpenCode command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=OPENCODE_TIMEOUT_SECONDS,
            cwd=cwd,
            env={**os.environ},
        )

        if result.returncode == 0:
            output = parse_opencode_output(result.stdout)
            logger.info(
                f"OpenCode subprocess completed successfully, "
                f"output_len={len(output)}"
            )
            return {
                "success": True,
                "output": output,
                "error": None,
                "session_id": session_id,
            }
        else:
            error_msg = (
                result.stderr.strip()
                if result.stderr
                else f"Exit code {result.returncode}"
            )
            logger.error(f"OpenCode subprocess failed: {error_msg}")
            return {
                "success": False,
                "output": "",
                "error": error_msg,
                "session_id": None,
            }

    except subprocess.TimeoutExpired:
        logger.error(f"OpenCode subprocess timed out after {OPENCODE_TIMEOUT_SECONDS}s")
        return {
            "success": False,
            "output": "",
            "error": (
                f"OpenCode process timed out after "
                f"{OPENCODE_TIMEOUT_SECONDS} seconds"
            ),
            "session_id": None,
        }
    except Exception as e:
        logger.error(f"Error running OpenCode subprocess: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "session_id": None,
        }
