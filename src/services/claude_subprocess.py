#!/usr/bin/env python3
"""Run Claude Code SDK in a subprocess to avoid event loop blocking issues."""

import asyncio
import json
import logging
import os
import sys
from typing import AsyncGenerator, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

# Derive project root from this file's location (src/services/claude_subprocess.py -> ../../)
_PROJECT_ROOT = str(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

# Timeout for Claude execution
CLAUDE_TIMEOUT_SECONDS = 300  # Per-message timeout (5 minutes)

# Sentinel markers for robust output extraction
SENTINEL_START = "---TGAGENT_OUTPUT_START---"
SENTINEL_END = "---TGAGENT_OUTPUT_END---"


def extract_between_sentinels(raw_output: str) -> str | None:
    """Extract content between sentinel markers from raw subprocess output.

    Finds the first occurrence of SENTINEL_START and SENTINEL_END and returns
    the stripped content between them. Returns None if either marker is missing,
    which signals the caller to fall back to line-by-line parsing.

    Args:
        raw_output: The raw subprocess output string, potentially containing
            debug logs, stderr contamination, or other noise.

    Returns:
        The stripped content between sentinel markers, or None if markers
        are not found (both must be present).
    """
    start_idx = raw_output.find(SENTINEL_START)
    if start_idx == -1:
        return None

    end_idx = raw_output.find(SENTINEL_END, start_idx + len(SENTINEL_START))
    if end_idx == -1:
        return None

    content = raw_output[start_idx + len(SENTINEL_START) : end_idx]
    return content.strip()


# Overall session timeout - loaded from settings at runtime, default 30 minutes
def get_session_timeout() -> int:
    """Get session timeout from settings."""
    try:
        from src.core.config import get_settings

        return get_settings().claude_session_timeout_seconds
    except Exception:
        return 1800  # Default 30 minutes if settings unavailable


def _get_session_timeout() -> int:
    """Lazy wrapper — evaluated at call time, not import time."""
    return get_session_timeout()


# Error patterns indicating a corrupted/invalid session that should be retried fresh
_SESSION_RETRY_PATTERNS = [
    "exit code -5",
    "Fatal error in message reader",
]


def _is_session_error(error_content: str) -> bool:
    """Check if error indicates a corrupted session that should be retried fresh."""
    lower = error_content.lower()
    return any(p.lower() in lower for p in _SESSION_RETRY_PATTERNS)


async def _graceful_shutdown(process, timeout_seconds: float = 5.0) -> None:
    """
    Attempt graceful shutdown with SIGTERM before SIGKILL.

    Args:
        process: The subprocess to shutdown
        timeout_seconds: How long to wait for graceful exit before force kill
    """
    try:
        # Try graceful termination first (SIGTERM)
        logger.debug(f"Sending SIGTERM to process {process.pid}")
        process.terminate()

        # Wait for graceful exit
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            logger.debug(f"Process {process.pid} exited gracefully")
            return
        except asyncio.TimeoutError:
            # Graceful exit failed, force kill
            logger.warning(
                f"Process {process.pid} did not exit gracefully, sending SIGKILL"
            )
            process.kill()
            await process.wait()
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")
        # Ensure process is killed
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass


def _encode_path_as_claude_dir(path: str) -> str:
    """Encode a filesystem path the way Claude Code SDK does for project dirs.

    The SDK replaces ``/`` and ``_`` with ``-``.
    Example: ``/Users/server/ai_projects/telegram_agent``
             -> ``-Users-server-ai-projects-telegram-agent``
    """
    # Strip trailing slash to avoid a trailing dash
    return path.rstrip("/").replace("/", "-").replace("_", "-")


def _decode_claude_dir_to_path(encoded_name: str) -> Optional[str]:
    """Reverse a Claude SDK encoded directory name back to a real filesystem path.

    Because both ``/`` and ``_`` are mapped to ``-``, reversal is ambiguous.
    We use a two-step strategy:

    1. **Naive reversal** – replace all ``-`` with ``/``.  If that path exists
       on disk we are done (works for paths that contain no underscores).
    2. **Forward-match scan** – walk the naive path component-by-component,
       checking the filesystem at each level for underscore variants.  This
       resolves paths like ``ai_projects`` without any hardcoded map.

    Returns the real path string, or ``None`` if it cannot be resolved.
    """
    from pathlib import Path

    if not encoded_name.startswith("-"):
        return None

    # Step 1: naive reversal (all dashes become slashes)
    naive_path = "/" + encoded_name[1:].replace("-", "/")
    if Path(naive_path).exists():
        return naive_path

    # Step 2: walk component-by-component to resolve underscore ambiguity
    # Split the encoded name (skip the leading dash) into parts
    parts = encoded_name[1:].split("-")
    # Try to reconstruct the real path by checking the filesystem
    resolved = _resolve_path_parts(parts)
    if resolved:
        return resolved

    # Unable to resolve — return the naive guess (caller can decide)
    logger.debug(
        f"Could not verify path for encoded dir '{encoded_name}', "
        f"using naive reversal: {naive_path}"
    )
    return naive_path


def _resolve_path_parts(parts: list) -> Optional[str]:
    """Try to reconstruct a filesystem path from encoded dash-separated parts.

    At each directory level, we try joining the next N parts with underscores
    (and without) to find an existing directory on disk.  This handles
    directories like ``ai_projects`` which are encoded as ``ai-projects``.

    Returns the resolved path string, or None if resolution fails.
    """
    from pathlib import Path

    current = Path("/")
    i = 0

    while i < len(parts):
        # Try progressively longer underscore-joined combinations
        found = False
        # Try from longest possible component down to a single part
        for length in range(len(parts) - i, 0, -1):
            candidate_parts = parts[i : i + length]
            # Try with underscores joining them
            candidate_underscore = "_".join(candidate_parts)
            if (current / candidate_underscore).exists():
                current = current / candidate_underscore
                i += length
                found = True
                break
            # For single part, also try as-is (no underscore needed)
            if length == 1:
                candidate_plain = candidate_parts[0]
                if (current / candidate_plain).exists():
                    current = current / candidate_plain
                    i += 1
                    found = True
                    break

        if not found:
            # No existing directory found at this level — resolution failed
            return None

    result = str(current)
    if Path(result).exists():
        return result
    return None


def find_session_cwd(session_id: str) -> Optional[str]:
    """Search for session file across known project directories.

    Claude Code SDK stores sessions in project-specific directories:
    ``~/.claude/projects/<encoded-path>/<session-id>.jsonl``

    The encoded path replaces ``/`` and ``_`` with ``-``.  This function
    finds the session file and dynamically resolves the original filesystem
    path without any hardcoded path mapping.

    Args:
        session_id: The Claude session ID to search for

    Returns:
        The CWD path where the session was found, or None if not found
    """
    from pathlib import Path

    claude_dir = Path.home() / ".claude" / "projects"

    if not claude_dir.exists():
        logger.debug(
            f"Session {session_id[:8]}... not found — {claude_dir} does not exist"
        )
        return None

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        session_file = project_dir / f"{session_id}.jsonl"
        if session_file.exists():
            project_name = project_dir.name
            cwd = _decode_claude_dir_to_path(project_name)
            if cwd:
                logger.info(f"Found session {session_id[:8]}... in project: {cwd}")
                return cwd

    logger.debug(
        f"Session {session_id[:8]}... not found in any known project directory"
    )
    return None


def _validate_cwd(cwd: str) -> str:
    """Validate cwd is within allowed directories.

    Prevents arbitrary directory access by ensuring the working directory
    is within a set of allowed base paths.

    Args:
        cwd: The working directory path to validate

    Returns:
        The resolved absolute path if valid

    Raises:
        ValueError: If cwd is not within allowed paths
    """
    from pathlib import Path

    resolved = Path(cwd).expanduser().resolve()

    # Allowed base directories
    allowed_bases = [
        Path.home() / "Research" / "vault",
        Path.home() / "ai_projects",
        Path("/tmp"),
        Path("/private/tmp"),
    ]

    for base in allowed_bases:
        try:
            if resolved.is_relative_to(base.resolve()):
                return str(resolved)
        except (ValueError, OSError):
            continue

    raise ValueError(f"Work directory not in allowed paths: {cwd}")


def get_configured_tools(override: list = None) -> list:
    """Resolve the Claude Code tool list from config.

    Priority:
    1. Explicit override (passed by caller)
    2. CLAUDE_ALLOWED_TOOLS env / Settings field (comma-separated)
    3. config/defaults.yaml → claude_tools.allowed_tools
    4. Hardcoded fallback

    Then CLAUDE_DISALLOWED_TOOLS / claude_tools.disallowed_tools are subtracted.
    """
    DEFAULT_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]

    # Start with override if provided
    if override is not None:
        tools = list(override)
    else:
        # Try Settings (env var CLAUDE_ALLOWED_TOOLS)
        try:
            from src.core.config import get_config_value, get_settings

            settings = get_settings()
            if settings.claude_allowed_tools:
                tools = [
                    t.strip()
                    for t in settings.claude_allowed_tools.split(",")
                    if t.strip()
                ]
            else:
                # Try YAML config
                yaml_tools = get_config_value("claude_tools.allowed_tools")
                if yaml_tools and isinstance(yaml_tools, list) and len(yaml_tools) > 0:
                    tools = list(yaml_tools)
                else:
                    tools = list(DEFAULT_TOOLS)
        except Exception:
            tools = list(DEFAULT_TOOLS)

    # Apply disallowed list
    try:
        from src.core.config import get_config_value, get_settings

        settings = get_settings()
        disallowed = []
        if settings.claude_disallowed_tools:
            disallowed = [
                t.strip()
                for t in settings.claude_disallowed_tools.split(",")
                if t.strip()
            ]
        else:
            yaml_disallowed = get_config_value("claude_tools.disallowed_tools")
            if yaml_disallowed and isinstance(yaml_disallowed, list):
                disallowed = yaml_disallowed
        if disallowed:
            tools = [t for t in tools if t not in disallowed]
            logger.info(
                f"Claude tools after disallow filter: {tools} (removed: {disallowed})"
            )
    except Exception:
        pass

    return tools


async def execute_claude_subprocess(
    prompt: str,
    cwd: str = None,
    model: str = "opus",
    allowed_tools: list = None,
    system_prompt: str = None,
    stop_check: callable = None,
    session_id: str = None,
    cleanup_callback: Optional[Callable[[], None]] = None,
    thinking_effort: str = None,
) -> AsyncGenerator[Tuple[str, str, Optional[str]], None]:
    """
    Execute Claude Code SDK in a subprocess and yield results.

    Wraps _execute_subprocess_once with automatic retry: if resuming a
    session fails with a session error (e.g. exit code -5), retries
    with a fresh session.
    """
    original_session_id = session_id
    original_cwd = cwd

    if not original_session_id:
        async for result in _execute_subprocess_once(
            prompt,
            cwd,
            model,
            allowed_tools,
            system_prompt,
            stop_check,
            session_id,
            cleanup_callback,
            thinking_effort,
        ):
            yield result
        return

    # Attempting session resume — watch for session errors
    has_content = False
    session_error = False

    async for result in _execute_subprocess_once(
        prompt,
        cwd,
        model,
        allowed_tools,
        system_prompt,
        stop_check,
        session_id,
        cleanup_callback,
        thinking_effort,
    ):
        msg_type = result[0]
        content = result[1]

        if msg_type in ("text", "tool", "done"):
            has_content = True
            yield result
        elif (
            msg_type == "error"
            and not has_content
            and (session_error or _is_session_error(content))
        ):
            # Suppress session errors — will retry fresh
            session_error = True
        else:
            yield result

    if session_error:
        logger.warning(
            f"Session {original_session_id[:8]}... resume failed with session error, "
            f"retrying with fresh session"
        )
        async for result in _execute_subprocess_once(
            prompt,
            original_cwd,
            model,
            allowed_tools,
            system_prompt,
            stop_check,
            None,
            cleanup_callback,
            thinking_effort,
        ):
            yield result


async def _execute_subprocess_once(
    prompt: str,
    cwd: str = None,
    model: str = "opus",
    allowed_tools: list = None,
    system_prompt: str = None,
    stop_check: callable = None,
    session_id: str = None,
    cleanup_callback: Optional[Callable[[], None]] = None,
    thinking_effort: str = None,
) -> AsyncGenerator[Tuple[str, str, Optional[str]], None]:
    """
    Execute Claude Code SDK in a single subprocess attempt.

    Args:
        stop_check: Optional callable that returns True if execution should stop
        session_id: Optional session ID to resume a previous conversation
        cleanup_callback: Optional callback to run on timeout/error cleanup

    Yields:
        Tuples of (msg_type, content, session_id)
        msg_type: "text", "tool", "init", "done", "error"
    """
    # Default cwd to project root if not provided
    if cwd is None:
        cwd = _PROJECT_ROOT

    allowed_tools = get_configured_tools(allowed_tools)

    # If resuming a session, try to find its original CWD
    if session_id:
        discovered_cwd = find_session_cwd(session_id)
        if discovered_cwd:
            if discovered_cwd != cwd:
                logger.warning(
                    f"Session {session_id[:8]}... was created in {discovered_cwd}, "
                    f"but requested CWD is {cwd}. Using original CWD to ensure session can be found."
                )
                cwd = discovered_cwd
        else:
            # Session not found in filesystem - this might be a new session or error
            logger.debug(
                f"Session {session_id[:8]}... not found in filesystem, will attempt resume with provided CWD: {cwd}"
            )

    # Validate cwd to prevent arbitrary directory access
    cwd = _validate_cwd(cwd)

    # Build the subprocess script
    script = _build_claude_script(
        prompt, cwd, model, allowed_tools, system_prompt, session_id, thinking_effort
    )

    resume_info = f", resuming={session_id[:8]}..." if session_id else ""
    logger.info(
        f"Starting Claude subprocess with model={model}, cwd={cwd}{resume_info}"
    )

    # Verify script encoding before running
    try:
        script.encode("utf-8")
    except UnicodeEncodeError as e:
        logger.error(
            f"Script encoding error at position {e.start}-{e.end}: {repr(script[max(0,e.start-10):e.end+10])}"
        )
        yield ("error", f"Script encoding error: {e}", None)
        return

    try:
        # Run the script in a subprocess
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"},
        )
        logger.debug(f"Subprocess created with PID: {process.pid}")

        session_id = None
        session_start_time = asyncio.get_event_loop().time()

        # Sentinel tracking for robust output parsing
        inside_sentinel = False
        sentinel_ever_seen = False

        # Read output line by line
        while True:
            # Check overall session timeout
            timeout_secs = _get_session_timeout()
            session_elapsed = asyncio.get_event_loop().time() - session_start_time
            if session_elapsed > timeout_secs:
                logger.error(
                    f"Claude session exceeded overall timeout of {timeout_secs}s "
                    f"(elapsed: {session_elapsed:.0f}s)"
                )
                # Use graceful shutdown
                await _graceful_shutdown(process)
                # Call cleanup callback if provided
                if cleanup_callback:
                    try:
                        cleanup_callback()
                    except Exception as e:
                        logger.error(f"Error in cleanup callback: {e}")
                yield (
                    "error",
                    f"⏱️ Session timeout after {timeout_secs // 60} minutes",
                    None,
                )
                return

            # Check if stop was requested
            if stop_check and stop_check():
                logger.info("Stop check returned True, shutting down subprocess")
                await _graceful_shutdown(process)
                # Call cleanup callback if provided
                if cleanup_callback:
                    try:
                        cleanup_callback()
                    except Exception as e:
                        logger.error(f"Error in cleanup callback: {e}")
                yield ("error", "⏹️ Stopped by user", None)
                return
            try:
                line = await asyncio.wait_for(
                    process.stdout.readline(), timeout=CLAUDE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"Claude subprocess timed out after {CLAUDE_TIMEOUT_SECONDS}s (no output)"
                )
                await _graceful_shutdown(process)
                # Call cleanup callback if provided
                if cleanup_callback:
                    try:
                        cleanup_callback()
                    except Exception as e:
                        logger.error(f"Error in cleanup callback: {e}")
                yield (
                    "error",
                    f"⏱️ Timed out after {CLAUDE_TIMEOUT_SECONDS}s with no output",
                    None,
                )
                return

            if not line:
                break

            line = line.decode().strip()
            if not line:
                continue

            # Sentinel marker detection
            if line == SENTINEL_START:
                inside_sentinel = True
                sentinel_ever_seen = True
                logger.debug("Sentinel start marker detected")
                continue
            if line == SENTINEL_END:
                inside_sentinel = False
                logger.debug("Sentinel end marker detected")
                continue

            # When sentinels are in use, skip lines outside the markers
            if sentinel_ever_seen and not inside_sentinel:
                logger.debug(f"Skipping line outside sentinel markers: {line[:80]}")
                continue

            # Parse JSON output (inside sentinels, or fallback when
            # no sentinels present for backward compatibility)
            try:
                msg = json.loads(line)
                msg_type = msg.get("type")
                content = msg.get("content", "")

                if msg_type == "init":
                    session_id = msg.get("session_id")
                    logger.info(f"Claude session initialized: {session_id}")
                elif msg_type == "text":
                    yield ("text", content, None)
                elif msg_type == "tool":
                    yield ("tool", content, None)
                elif msg_type == "done":
                    session_id = msg.get("session_id", session_id)
                    stats = msg.get("stats", {})
                    logger.info(
                        f"Claude completed: session={session_id}, cost=${msg.get('cost', 0):.4f}"
                    )
                    yield ("done", json.dumps(stats), session_id)
                elif msg_type == "error":
                    logger.error(f"Claude error: {content}")
                    yield ("error", content, None)
            except json.JSONDecodeError:
                # Non-JSON output (debug/error)
                logger.debug(f"Claude subprocess output: {line}")

        # Wait for process to complete
        await process.wait()

        if process.returncode != 0:
            stderr = await process.stderr.read()
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"Claude subprocess failed: {error_msg}")
            yield ("error", f"Process failed: {error_msg[:200]}", None)

    except Exception as e:
        logger.error(f"Error running Claude subprocess: {e}")
        yield ("error", str(e), None)


def _sanitize_text(text: str) -> str:
    """Remove invalid UTF-8 surrogates from text.

    Surrogates (U+D800–U+DFFF) are invalid in UTF-8 and cause
    'surrogates not allowed' errors when encoding to JSON.
    """
    if not text:
        return text
    # First pass: encode with surrogatepass to preserve them, then replace
    # This handles surrogates that Python's string has internally
    try:
        text = text.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )
    except (UnicodeDecodeError, UnicodeEncodeError):
        # Fallback: use strict replacement
        text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")

    # Second pass: Remove any remaining surrogate characters via regex
    import re

    text = re.sub(r"[\ud800-\udfff]", "\ufffd", text)

    return text


def _build_claude_script(
    prompt: str,
    cwd: str,
    model: str,
    allowed_tools: list,
    system_prompt: Optional[str],
    session_id: Optional[str] = None,
    thinking_effort: Optional[str] = None,
) -> str:
    """Build the Python script to run in subprocess."""

    # Sanitize inputs to remove invalid UTF-8 surrogates
    original_len = len(prompt)
    prompt = _sanitize_text(prompt)
    if len(prompt) != original_len:
        logger.warning(f"Sanitized prompt: {original_len} -> {len(prompt)} chars")
    if system_prompt:
        system_prompt = _sanitize_text(system_prompt)

    # Escape the prompt and system prompt for embedding in script
    # Use ensure_ascii=False to keep emojis as UTF-8 rather than \uXXXX surrogates
    try:
        prompt_escaped = json.dumps(prompt, ensure_ascii=False)
    except UnicodeEncodeError as e:
        logger.error(f"JSON encode failed after sanitization: {e}")
        # Force ASCII encoding as fallback
        prompt_escaped = json.dumps(
            prompt.encode("ascii", errors="replace").decode("ascii")
        )
    system_prompt_escaped = (
        json.dumps(system_prompt, ensure_ascii=False) if system_prompt else "None"
    )
    session_id_escaped = (
        json.dumps(session_id, ensure_ascii=False) if session_id else "None"
    )
    tools_escaped = json.dumps(allowed_tools, ensure_ascii=False)
    thinking_effort_escaped = (
        json.dumps(thinking_effort, ensure_ascii=False) if thinking_effort else "None"
    )

    script = f"""
import asyncio
import json
import os
import sys
import time
from collections import Counter

# Unset API key to use subscription
os.environ.pop("ANTHROPIC_API_KEY", None)

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, SystemMessage, ResultMessage, TextBlock, ToolUseBlock

async def run():
    prompt = {prompt_escaped}
    cwd = {json.dumps(cwd)}
    model = {json.dumps(model)}
    allowed_tools = {tools_escaped}
    system_prompt = {system_prompt_escaped}
    resume_session = {session_id_escaped}
    thinking_effort = {thinking_effort_escaped}

    # Map thinking effort to token budget (low=4k, medium=10k, high=32k, max=128k)
    max_thinking_tokens = None
    if thinking_effort:
        effort_map = {{"low": 4000, "medium": 10000, "high": 32000, "max": 128000}}
        max_thinking_tokens = effort_map.get(thinking_effort, 10000)

    options = ClaudeAgentOptions(
        cwd=cwd,
        allowed_tools=allowed_tools,
        model=model,
        resume=resume_session,
        max_thinking_tokens=max_thinking_tokens,
    )
    if system_prompt:
        options = ClaudeAgentOptions(
            cwd=cwd,
            allowed_tools=allowed_tools,
            model=model,
            system_prompt=system_prompt,
            resume=resume_session,
            max_thinking_tokens=max_thinking_tokens,
        )

    # Track statistics
    start_time = time.time()
    tool_counts = Counter()
    files_read = set()
    files_written = set()
    web_fetches = []
    skills_used = set()
    bash_commands = []

    # Emit sentinel start marker for robust output parsing
    print("{SENTINEL_START}")
    sys.stdout.flush()

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, SystemMessage):
                if message.subtype == "init" and message.data:
                    session_id = message.data.get("session_id")
                    print(json.dumps({{"type": "init", "session_id": session_id}}))
                    sys.stdout.flush()

            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(json.dumps({{"type": "text", "content": block.text}}))
                        sys.stdout.flush()
                    elif isinstance(block, ToolUseBlock):
                        tool_name = block.name
                        tool_input = block.input if hasattr(block, 'input') else {{}}

                        # Track tool usage
                        tool_counts[tool_name] += 1

                        # Track specific operations
                        if tool_name == "Read":
                            path = tool_input.get("file_path", "")
                            if path:
                                files_read.add(path)
                        elif tool_name in ["Write", "Edit"]:
                            path = tool_input.get("file_path", "")
                            if path:
                                files_written.add(path)
                        elif tool_name == "WebFetch":
                            url = tool_input.get("url", "")
                            if url:
                                web_fetches.append(url)
                        elif tool_name == "WebSearch":
                            query_text = tool_input.get("query", "")
                            if query_text:
                                web_fetches.append(f"search: {{query_text[:40]}}")
                        elif tool_name == "Skill":
                            skill = tool_input.get("skill", "")
                            if skill:
                                skills_used.add(skill)
                        elif tool_name == "Bash":
                            cmd = tool_input.get("command", "")
                            if cmd:
                                bash_commands.append(cmd[:200])

                        tool_info = f"{{block.name}}: {{str(tool_input)[:100]}}"
                        print(json.dumps({{"type": "tool", "content": tool_info}}))
                        sys.stdout.flush()

            elif isinstance(message, ResultMessage):
                # Calculate duration
                duration_seconds = int(time.time() - start_time)
                duration_minutes = duration_seconds // 60
                duration_display = f"{{duration_minutes}}m {{duration_seconds % 60}}s" if duration_minutes > 0 else f"{{duration_seconds}}s"

                # Build statistics
                stats = {{
                    "duration": duration_display,
                    "duration_seconds": duration_seconds,
                    "tool_counts": dict(tool_counts),
                    "files_read": list(files_read),
                    "files_written": list(files_written),
                    "web_fetches": web_fetches,
                    "skills_used": list(skills_used),
                    "bash_commands": bash_commands,
                }}

                print(json.dumps({{
                    "type": "done",
                    "session_id": message.session_id,
                    "turns": message.num_turns,
                    "cost": message.total_cost_usd,
                    "stats": stats,
                }}))
                sys.stdout.flush()

    except Exception as e:
        print(json.dumps({{"type": "error", "content": str(e)}}))
        sys.stdout.flush()
        # Emit sentinel end marker even on error for consistent parsing
        print("{SENTINEL_END}")
        sys.stdout.flush()
        sys.exit(1)

    # Emit sentinel end marker
    print("{SENTINEL_END}")
    sys.stdout.flush()

asyncio.run(run())
"""
    return script
