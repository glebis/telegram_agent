#!/usr/bin/env python3
"""Run Claude Code SDK in a subprocess to avoid event loop blocking issues."""
import asyncio
import json
import logging
import os
import subprocess
import sys
from typing import AsyncGenerator, Tuple, Optional

logger = logging.getLogger(__name__)

# Timeout for Claude execution
CLAUDE_TIMEOUT_SECONDS = 300


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


async def execute_claude_subprocess(
    prompt: str,
    cwd: str = "/Users/server/Research/vault",
    model: str = "sonnet",
    allowed_tools: list = None,
    system_prompt: str = None,
    stop_check: callable = None,
    session_id: str = None,
) -> AsyncGenerator[Tuple[str, str, Optional[str]], None]:
    """
    Execute Claude Code SDK in a subprocess and yield results.

    This bypasses event loop blocking issues that occur when running
    the SDK inside uvicorn + telegram bot context.

    Args:
        stop_check: Optional callable that returns True if execution should stop
        session_id: Optional session ID to resume a previous conversation

    Yields:
        Tuples of (msg_type, content, session_id)
        msg_type: "text", "tool", "init", "done", "error"
    """
    if allowed_tools is None:
        allowed_tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]

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

        # Read output line by line
        while True:
            # Check if stop was requested
            if stop_check and stop_check():
                logger.info("Stop check returned True, killing subprocess")
                process.kill()
                yield ("error", "⏹️ Stopped by user", None)
                return
            try:
                line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=CLAUDE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.error(f"Claude subprocess timed out after {CLAUDE_TIMEOUT_SECONDS}s")
                process.kill()
                yield ("error", f"Timed out after {CLAUDE_TIMEOUT_SECONDS // 60} minutes", None)
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
                    logger.info(f"Claude completed: session={session_id}, cost=${msg.get('cost', 0):.4f}")
                    yield ("done", "", session_id)
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
                        tool_info = f"{{block.name}}: {{str(block.input)[:100]}}"
                        print(json.dumps({{"type": "tool", "content": tool_info}}))
                        sys.stdout.flush()

            elif isinstance(message, ResultMessage):
                print(json.dumps({{
                    "type": "done",
                    "session_id": message.session_id,
                    "turns": message.num_turns,
                    "cost": message.total_cost_usd,
                }}))
                sys.stdout.flush()

    except Exception as e:
        print(json.dumps({{"type": "error", "content": str(e)}}))
        sys.stdout.flush()
        sys.exit(1)

asyncio.run(run())
'''
    return script
