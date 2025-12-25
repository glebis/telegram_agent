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


async def execute_claude_subprocess(
    prompt: str,
    cwd: str = "/Users/server/Research/vault",
    model: str = "sonnet",
    allowed_tools: list = None,
    system_prompt: str = None,
) -> AsyncGenerator[Tuple[str, str, Optional[str]], None]:
    """
    Execute Claude Code SDK in a subprocess and yield results.

    This bypasses event loop blocking issues that occur when running
    the SDK inside uvicorn + telegram bot context.

    Yields:
        Tuples of (msg_type, content, session_id)
        msg_type: "text", "tool", "init", "done", "error"
    """
    if allowed_tools is None:
        allowed_tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]

    # Build the subprocess script
    script = _build_claude_script(prompt, cwd, model, allowed_tools, system_prompt)

    logger.info(f"Starting Claude subprocess with model={model}, cwd={cwd}")

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


def _build_claude_script(
    prompt: str,
    cwd: str,
    model: str,
    allowed_tools: list,
    system_prompt: Optional[str],
) -> str:
    """Build the Python script to run in subprocess."""

    # Escape the prompt and system prompt for embedding in script
    prompt_escaped = json.dumps(prompt)
    system_prompt_escaped = json.dumps(system_prompt) if system_prompt else "None"
    tools_escaped = json.dumps(allowed_tools)

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

    options = ClaudeCodeOptions(
        cwd=cwd,
        allowed_tools=allowed_tools,
        model=model,
    )
    if system_prompt:
        options = ClaudeCodeOptions(
            cwd=cwd,
            allowed_tools=allowed_tools,
            model=model,
            system_prompt=system_prompt,
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
