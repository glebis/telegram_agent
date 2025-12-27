"""Session emoji utilities for visual session identification.

Generates deterministic emoji pairs from session IDs for easy visual recognition.
Example: "🔴🟦 db5eesda3r"
"""

import hashlib

# Emoji sets for visual variety
EMOJI_CIRCLES = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "⚫", "⚪", "🟤"]
EMOJI_SQUARES = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪", "⬛", "⬜", "🟫"]


def get_session_emoji(session_id: str) -> str:
    """Generate a deterministic 2-emoji identifier from a session ID.

    Uses MD5 hash of session ID to select one emoji from each set,
    ensuring the same session always gets the same emoji pair.

    Args:
        session_id: The session UUID/ID string

    Returns:
        Two-emoji string like "🔴🟦"
    """
    if not session_id:
        return "⬜⬜"

    # Hash the session ID
    hash_bytes = hashlib.md5(session_id.encode()).digest()

    # Use first two bytes to select emojis
    circle_idx = hash_bytes[0] % len(EMOJI_CIRCLES)
    square_idx = hash_bytes[1] % len(EMOJI_SQUARES)

    return f"{EMOJI_CIRCLES[circle_idx]}{EMOJI_SQUARES[square_idx]}"


def format_session_id(session_id: str, short: bool = True) -> str:
    """Format a session ID with emoji prefix for display.

    Args:
        session_id: The full session ID
        short: If True, truncate ID to first 8 chars

    Returns:
        Formatted string like "🔴🟦 db5eesda"
    """
    if not session_id:
        return "⬜⬜ (none)"

    emoji = get_session_emoji(session_id)
    display_id = session_id[:8] if short else session_id

    return f"{emoji} {display_id}"
