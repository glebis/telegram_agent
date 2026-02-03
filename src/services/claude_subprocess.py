#!/usr/bin/env python3
"""Run Claude Code SDK in a subprocess to avoid event loop blocking issues."""
import asyncio
import json
import logging
import os
import subprocess
import sys
from typing import AsyncGenerator, Tuple, Optional, Callable

logger = logging.getLogger(__name__)

# Timeout for Claude execution
CLAUDE_TIMEOUT_SECONDS = 300  # Per-message timeout (5 minutes)

# Overall session timeout - loaded from settings at runtime, default 30 minutes
def get_session_timeout() -> int:
    """Get session timeout from settings."""
    try:
        from src.core.config import get_settings
        return get_settings().claude_session_timeout_seconds
    except Exception:
        return 1800  # Default 30 minutes if settings unavailable

CLAUDE_SESSION_TIMEOUT_SECONDS = get_session_timeout()


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
            logger.warning(f"Process {process.pid} did not exit gracefully, sending SIGKILL")
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


def find_session_cwd(session_id: str) -> Optional[str]:
    """Search for session file across known project directories.

    Claude Code SDK stores sessions in project-specific directories:
    ~/.claude/projects/<project-path>/<session-id>.jsonl

    This function searches known projects for a session file and returns
    the CWD where it was found.

    Args:
        session_id: The Claude session ID to search for

    Returns:
        The CWD path where the session was found, or None if not found
    """
    from pathlib import Path

    claude_dir = Path.home() / ".claude" / "projects"

    # Also check all existing project directories dynamically
    if claude_dir.exists():
        for project_dir in claude_dir.iterdir():
            if not project_dir.is_dir():
                continue
            session_file = project_dir / f"{session_id}.jsonl"
            if session_file.exists():
                # Convert project directory name back to actual path
                # Claude Code SDK encodes paths by:
                # 1. Replacing "/" with "-" in the full path
                # 2. Converting "_" to "-" as well
                # So: /Users/server/ai_projects/telegram_agent → -Users-server-ai-projects-telegram-agent
                #
                # To reverse, we try to match against known paths first
                project_name = project_dir.name

                # Map of encoded names to actual paths
                project_map = {
                    "-Users-server-ai-projects-telegram-agent": "/Users/server/ai_projects/telegram_agent",
                    "-Users-server-Research-vault": "/Users/server/Research/vault",
                    "-Users-server-Research-vault-Research-daily": "/Users/server/Research/vault/Research/daily",
                }

                if project_name in project_map:
                    cwd = project_map[project_name]
                    logger.info(f"Found session {session_id[:8]}... in project: {cwd}")
                    return cwd
                else:
                    # Fallback: just replace dashes with slashes (may be incorrect for underscores)
                    if project_name.startswith("-"):
                        cwd = "/" + project_name[1:].replace("-", "/")
                        logger.warning(
                            f"Found session {session_id[:8]}... in unknown project format: {project_name}. "
                            f"Using best-guess CWD: {cwd} (may be incorrect if path contains underscores)"
                        )
                        return cwd

    logger.debug(f"Session {session_id[:8]}... not found in any known project directory")
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
            from src.core.config import get_settings, get_config_value
            settings = get_settings()
            if settings.claude_allowed_tools:
                tools = [t.strip() for t in settings.claude_allowed_tools.split(",") if t.strip()]
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
        from src.core.config import get_settings, get_config_value
        settings = get_settings()
        disallowed = []
        if settings.claude_disallowed_tools:
            disallowed = [t.strip() for t in settings.claude_disallowed_tools.split(",") if t.strip()]
        else:
            yaml_disallowed = get_config_value("claude_tools.disallowed_tools")
            if yaml_disallowed and isinstance(yaml_disallowed, list):
                disallowed = yaml_disallowed
        if disallowed:
            tools = [t for t in tools if t not in disallowed]
            logger.info(f"Claude tools after disallow filter: {tools} (removed: {disallowed})")
    except Exception:
        pass

    return tools


async def execute_claude_subprocess(
    prompt: str,
    cwd: str = "/Users/server/Research/vault",
    model: str = "sonnet",
    allowed_tools: list = None,
    system_prompt: str = None,
    stop_check: callable = None,
    session_id: str = None,
    cleanup_callback: Optional[Callable[[], None]] = None,
) -> AsyncGenerator[Tuple[str, str, Optional[str]], None]:
    """
    Execute Claude Code SDK in a subprocess and yield results.

    This bypasses event loop blocking issues that occur when running
    the SDK inside uvicorn + telegram bot context.

    Args:
        stop_check: Optional callable that returns True if execution should stop
        session_id: Optional session ID to resume a previous conversation
        cleanup_callback: Optional callback to run on timeout/error cleanup

    Yields:
        Tuples of (msg_type, content, session_id)
        msg_type: "text", "tool", "init", "done", "error"
    """
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
            logger.debug(f"Session {session_id[:8]}... not found in filesystem, will attempt resume with provided CWD: {cwd}")

    # Validate cwd to prevent arbitrary directory access
    cwd = _validate_cwd(cwd)

    # Build the subprocess script
    script = _build_claude_script(prompt, cwd, model, allowed_tools, system_prompt, session_id)

    resume_info = f", resuming={session_id[:8]}..." if session_id else ""
    logger.info(f"Starting Claude subprocess with model={model}, cwd={cwd}{resume_info}")

    # Verify script encoding before running
    try:
        script.encode('utf-8')
    except UnicodeEncodeError as e:
        logger.error(f"Script encoding error at position {e.start}-{e.end}: {repr(script[max(0,e.start-10):e.end+10])}")
        yield ("error", f"Script encoding error: {e}", None)
        return

    try:
        # Run the script in a subprocess
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ANTHROPIC_API_KEY": ""},  # Unset to use subscription
        )
        logger.debug(f"Subprocess created with PID: {process.pid}")

        session_id = None
        session_start_time = asyncio.get_event_loop().time()

        # Read output line by line
        while True:
            # Check overall session timeout
            session_elapsed = asyncio.get_event_loop().time() - session_start_time
            if session_elapsed > CLAUDE_SESSION_TIMEOUT_SECONDS:
                logger.error(
                    f"Claude session exceeded overall timeout of {CLAUDE_SESSION_TIMEOUT_SECONDS}s "
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
                yield ("error", f"⏱️ Session timeout after {CLAUDE_SESSION_TIMEOUT_SECONDS // 60} minutes", None)
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
                    process.stdout.readline(),
                    timeout=CLAUDE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.error(f"Claude subprocess timed out after {CLAUDE_TIMEOUT_SECONDS}s (no output)")
                await _graceful_shutdown(process)
                # Call cleanup callback if provided
                if cleanup_callback:
                    try:
                        cleanup_callback()
                    except Exception as e:
                        logger.error(f"Error in cleanup callback: {e}")
                yield ("error", f"⏱️ Timed out after {CLAUDE_TIMEOUT_SECONDS}s with no output", None)
                return

            if not line:
                break

            line = line.decode().strip()
            if not line:
                continue

            # Parse JSON output
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
                    logger.info(f"Claude completed: session={session_id}, cost=${msg.get('cost', 0):.4f}")
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
        text = text.encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')
    except (UnicodeDecodeError, UnicodeEncodeError):
        # Fallback: use strict replacement
        text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')

    # Second pass: Remove any remaining surrogate characters via regex
    import re
    text = re.sub(r'[\ud800-\udfff]', '\ufffd', text)

    return text


def _build_claude_script(
    prompt: str,
    cwd: str,
    model: str,
    allowed_tools: list,
    system_prompt: Optional[str],
    session_id: Optional[str] = None,
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
        prompt_escaped = json.dumps(prompt.encode('ascii', errors='replace').decode('ascii'))
    system_prompt_escaped = json.dumps(system_prompt, ensure_ascii=False) if system_prompt else "None"
    session_id_escaped = json.dumps(session_id, ensure_ascii=False) if session_id else "None"
    tools_escaped = json.dumps(allowed_tools, ensure_ascii=False)

    script = f'''
import asyncio
import json
import os
import sys
import time
from collections import Counter

# Unset API key to use subscription
os.environ.pop("ANTHROPIC_API_KEY", None)

from claude_code_sdk import query, ClaudeCodeOptions
from claude_code_sdk.types import AssistantMessage, SystemMessage, ResultMessage, TextBlock, ToolUseBlock

async def run():
    prompt = {prompt_escaped}
    cwd = {json.dumps(cwd)}
    model = {json.dumps(model)}
    allowed_tools = {tools_escaped}
    system_prompt = {system_prompt_escaped}
    resume_session = {session_id_escaped}

    options = ClaudeCodeOptions(
        cwd=cwd,
        allowed_tools=allowed_tools,
        model=model,
        resume=resume_session,
    )
    if system_prompt:
        options = ClaudeCodeOptions(
            cwd=cwd,
            allowed_tools=allowed_tools,
            model=model,
            system_prompt=system_prompt,
            resume=resume_session,
        )

    # Track statistics
    start_time = time.time()
    tool_counts = Counter()
    files_read = set()
    files_written = set()
    web_fetches = []
    skills_used = set()
    bash_commands = []

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
                                files_read.add(path.split("/")[-1])
                        elif tool_name in ["Write", "Edit"]:
                            path = tool_input.get("file_path", "")
                            if path:
                                files_written.add(path.split("/")[-1])
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
                                bash_commands.append(cmd[:50])

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
        sys.exit(1)

asyncio.run(run())
'''
    return script
