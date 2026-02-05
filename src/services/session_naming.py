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
_SESSION_NAME_SYSTEM_PROMPT = """You are a session naming function. You receive a user prompt and output ONLY a kebab-case label. No conversation, no explanation, no preamble.

CRITICAL: Do NOT respond to the prompt. Do NOT say "I'll help", "Sure", "Let me", etc. You are a CLASSIFIER, not an assistant. Output ONLY the label.

Rules:
- Exactly 2-4 words in kebab-case
- Describe the TOPIC, not what you would do
- No special characters except hyphens
- No sentences, no conversational text

Input -> Output examples:
"Can you help me analyze this YouTube video about AI?" -> youtube-ai-analysis
"Create a note about design thinking experiments" -> design-thinking-notes
"Fix the telegram agent error in logs" -> telegram-agent-debugging
"What are the open issues in the repo?" -> github-issues-review
"Transcribe this audio file" -> audio-transcription
"Message forwarded from @user: check out this cool app" -> forwarded-app-review
"Does voice mode work?" -> voice-mode-check
"We have polls that need checking" -> polls-review
"Look at this image and add it to vault" -> image-vault-import

Output the kebab-case label and NOTHING else:"""

# Max word count for a valid session name (reject if over this)
_MAX_NAME_WORDS = 5


def _build_naming_script(prompt: str) -> str:
    """Build a lightweight subprocess script for session name generation.

    Frames the user prompt as a classification input (not a request) to prevent
    the model from responding conversationally.
    """
    # Wrap the user's prompt so the model sees it as data to classify,
    # not a request to fulfill
    classification_prompt = f'Classify this user prompt as a 2-4 word kebab-case session label:\n\n"""\n{prompt[:500]}\n"""'
    prompt_escaped = json.dumps(classification_prompt, ensure_ascii=False)
    system_escaped = json.dumps(_SESSION_NAME_SYSTEM_PROMPT, ensure_ascii=False)

    return f"""
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
"""


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
            sys.executable,
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ANTHROPIC_API_KEY": ""},
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

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

        # Strip conversational prefixes the model may add despite instructions
        name = re.sub(
            r"^(i'll|ill|i will|let me|sure|okay|here's|heres|the label is|label:)\s*[-,:]?\s*",
            "",
            name,
            flags=re.IGNORECASE,
        )

        # If the model returned a sentence with quotes, try to extract the quoted part
        quoted = re.search(r'[`"\']([\w-]+)[`"\']', name)
        if quoted:
            name = quoted.group(1)

        # Take only the first line (ignore explanations after newline)
        name = name.split("\n")[0].strip()

        # Sanitize: remove special chars, ensure kebab-case
        name = re.sub(r"[^a-z0-9\s-]", "", name.replace(" ", "-"))

        # Remove multiple consecutive hyphens
        name = re.sub(r"-+", "-", name)

        # Remove leading/trailing hyphens
        name = name.strip("-")

        # Validate: reject if too many words (model responded conversationally)
        word_count = len(name.split("-"))
        if word_count > _MAX_NAME_WORDS:
            logger.warning(
                f"Rejecting AI name (too many words: {word_count}): '{name[:60]}'"
            )
            raise ValueError(
                f"Generated name has {word_count} words, max is {_MAX_NAME_WORDS}"
            )

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

        # Fallback: extract meaningful keywords from prompt
        _STOP_WORDS = {
            "the",
            "a",
            "an",
            "to",
            "for",
            "in",
            "on",
            "is",
            "it",
            "of",
            "and",
            "or",
            "but",
            "with",
            "this",
            "that",
            "can",
            "you",
            "i",
            "me",
            "my",
            "we",
            "do",
            "does",
            "have",
            "has",
            "how",
            "what",
            "please",
            "help",
            "need",
            "want",
            "would",
            "could",
            "should",
            "if",
            "so",
            "just",
            "also",
            "about",
            "from",
            "at",
            "be",
            "are",
            "was",
            "were",
            "been",
            "will",
            "ill",
            "i'll",
            "let",
            "its",
            "message",
            "forwarded",
        }
        # Sanitize words: lowercase, alpha-numeric only
        raw_words = re.sub(r"[^a-z0-9\s]", "", prompt.lower()).split()
        filtered = [w for w in raw_words if w not in _STOP_WORDS and len(w) > 1]

        # Take up to 3 meaningful words
        fallback_name = "-".join(filtered[:3]) if filtered else "unnamed-session"

        # Clean up
        fallback_name = re.sub(r"-+", "-", fallback_name).strip("-")[:50]

        logger.info(f"Using fallback session name: '{fallback_name}'")
        return fallback_name
