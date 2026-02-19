"""
Session service — business logic for session trigger detection.

Extracted from src/bot/handlers/claude_commands.py (#218).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Trigger phrases that start a new session (case-insensitive)
NEW_SESSION_TRIGGERS = [
    "new session",
    "start new session",
    "fresh session",
    "новая сессия",  # Russian
]


def detect_new_session_trigger(text: Optional[str]) -> dict:
    """
    Detect if text starts with a 'new session' trigger phrase.

    Args:
        text: The message text to check

    Returns:
        dict with:
            - triggered: bool - True if trigger phrase detected
            - prompt: str - Text after the trigger phrase (or original text)
    """
    if not text:
        return {"triggered": False, "prompt": text or ""}

    text_lower = text.lower().strip()

    for trigger in NEW_SESSION_TRIGGERS:
        if text_lower.startswith(trigger):
            # Extract the prompt after the trigger phrase
            remainder = text[len(trigger) :].strip()
            # Handle newlines - take everything after trigger
            remainder = remainder.lstrip("\n").strip()
            return {"triggered": True, "prompt": remainder}

    return {"triggered": False, "prompt": text}
