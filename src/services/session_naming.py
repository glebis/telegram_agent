"""Service for generating AI-powered session names from prompts.

Uses the Claude Code SDK (subprocess) to avoid requiring ANTHROPIC_API_KEY.
"""

import asyncio
import json
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)

# System prompt for session name generation
_SESSION_NAME_SYSTEM_PROMPT = """Generate a concise 2-4 word session name from the user's prompt.

Rules:
- Maximum 4 words
- Descriptive and specific
- Use kebab-case (lowercase with hyphens)
- No special characters except hyphens
- Capture the main action and subject
- Examples:
  * "Can you help me analyze this YouTube video about AI?" -> "youtube-ai-analysis"
  * "Create a note about design thinking experiments" -> "design-thinking-notes"
  * "Fix the telegram agent error in logs" -> "telegram-agent-debugging"
  * "What are the open issues in the repo?" -> "github-issues-review"
  * "Transcribe this audio file" -> "audio-transcription"

Return ONLY the kebab-case name, nothing else."""


def _build_naming_script(prompt: str) -> str:
    """Build a lightweight subprocess script for session name generation."""
    prompt_escaped = json.dumps(prompt[:500], ensure_ascii=False)
    system_escaped = json.dumps(_SESSION_NAME_SYSTEM_PROMPT, ensure_ascii=False)

    return f'''
import asyncio
import json
import os
import sys

# Unset API key to use subscription
os.environ.pop("ANTHROPIC_API_KEY", None)

from claude_code_sdk import query, ClaudeCodeOptions
from claude_code_sdk.types import AssistantMessage, ResultMessage, TextBlock

async def run():
    prompt = {prompt_escaped}
    system_prompt = {system_escaped}

    options = ClaudeCodeOptions(
        max_turns=1,
        model="haiku",
        system_prompt=system_prompt,
        allowed_tools=[],
    )

    result_text = ""
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text

        print(json.dumps({{"type": "result", "text": result_text}}))
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({{"type": "error", "text": str(e)}}))
        sys.stdout.flush()
        sys.exit(1)

asyncio.run(run())
'''


async def generate_session_name(prompt: str) -> str:
    """Generate a concise 2-4 word session name from prompt.

    Uses Claude Code SDK (subprocess) with the haiku model for fast,
    cost-efficient name generation. No API key required -- uses the
    user's Claude subscription.

    Args:
        prompt: The user's first prompt to the session

    Returns:
        A kebab-case session name (e.g., "youtube-ai-analysis")

    Examples:
        "Can you help me analyze this YouTube video about AI?"
        -> "youtube-ai-analysis"

        "Create a note about design thinking experiments"
        -> "design-thinking-notes"

        "Fix the telegram agent error in logs"
        -> "telegram-agent-debugging"
    """
    try:
        script = _build_naming_script(prompt)

        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ANTHROPIC_API_KEY": ""},
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=30
        )

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"Naming subprocess failed: {error_msg[:200]}")

        # Parse the JSON result from stdout
        name = None
        for line in stdout.decode().strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("type") == "result":
                    name = msg.get("text", "").strip().lower()
                elif msg.get("type") == "error":
                    raise RuntimeError(msg.get("text", "Unknown SDK error"))
            except json.JSONDecodeError:
                continue

        if not name:
            raise ValueError("No text returned from Claude SDK")

        # Sanitize: remove special chars, ensure kebab-case
        name = re.sub(r'[^a-z0-9-]', '', name.replace(' ', '-'))

        # Remove multiple consecutive hyphens
        name = re.sub(r'-+', '-', name)

        # Remove leading/trailing hyphens
        name = name.strip('-')

        # Limit length to 50 chars
        name = name[:50]

        # Ensure we have something
        if not name:
            logger.warning("Generated empty session name, using fallback")
            raise ValueError("Empty session name generated")

        logger.info(f"Generated session name: '{name}' from prompt: '{prompt[:50]}...'")
        return name

    except Exception as e:
        logger.error(f"Failed to generate session name: {e}")

        # Fallback: use first 3-4 words of prompt
        words = prompt.lower().split()[:4]
        # Remove common articles/prepositions
        filtered = [w for w in words if w not in {'the', 'a', 'an', 'to', 'for', 'in', 'on'}]

        # Take up to 3 meaningful words
        fallback_name = '-'.join(filtered[:3]) if filtered else 'unnamed-session'

        # Sanitize fallback
        fallback_name = re.sub(r'[^a-z0-9-]', '', fallback_name)[:50]

        logger.info(f"Using fallback session name: '{fallback_name}'")
        return fallback_name
