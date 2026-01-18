"""Service for generating AI-powered session names from prompts."""

import logging
import os
import re
from typing import Optional

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# Initialize Anthropic client for session naming
_anthropic_client: Optional[AsyncAnthropic] = None


def get_anthropic_client() -> AsyncAnthropic:
    """Get or create the Anthropic client for session naming."""
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")
        _anthropic_client = AsyncAnthropic(api_key=api_key)
    return _anthropic_client


async def generate_session_name(prompt: str) -> str:
    """Generate a concise 2-4 word session name from prompt.

    Uses Claude Haiku for fast, cost-efficient name generation (~$0.001 per session).

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
    system_prompt = """Generate a concise 2-4 word session name from the user's prompt.

Rules:
- Maximum 4 words
- Descriptive and specific
- Use kebab-case (lowercase with hyphens)
- No special characters except hyphens
- Capture the main action and subject
- Examples:
  * "Can you help me analyze this YouTube video about AI?" → "youtube-ai-analysis"
  * "Create a note about design thinking experiments" → "design-thinking-notes"
  * "Fix the telegram agent error in logs" → "telegram-agent-debugging"
  * "What are the open issues in the repo?" → "github-issues-review"
  * "Transcribe this audio file" → "audio-transcription"

Return ONLY the kebab-case name, nothing else."""

    try:
        client = get_anthropic_client()

        response = await client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=50,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt[:500]}],  # Limit prompt length
        )

        # Extract text from response
        name = response.content[0].text.strip().lower()

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
