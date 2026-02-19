"""
User-facing error message sanitization.

Maps exception types and patterns to friendly, safe messages that
never expose internal details (file paths, API keys, stack traces, etc.)
to Telegram users.

Usage:
    from src.core.error_messages import sanitize_error

    try:
        ...
    except Exception as e:
        logger.error(f"Operation failed: {e}", exc_info=True)
        user_msg = sanitize_error(e, context="processing your image")
        await message.reply_text(f"Sorry, {user_msg}")
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Default fallback for any unrecognised exception
_DEFAULT_MESSAGE = "Something went wrong. Please try again later."

# Maps exception types to user-friendly messages.
# Order matters: more specific types first.
_TYPE_MAP: dict[type, str] = {
    ConnectionError: (
        "Could not connect to the service. Please try again in a moment."
    ),
    TimeoutError: (
        "The request took too long to complete. Please try again."
    ),
    PermissionError: (
        "A permissions issue occurred. Please try again or contact support."
    ),
    FileNotFoundError: (
        "A required resource could not be found. Please try again."
    ),
    KeyError: (
        "A configuration issue occurred. Please try again later."
    ),
    ValueError: (
        "The request could not be processed. Please try again."
    ),
}

# Patterns matched against str(e).lower() for keyword-based detection.
# Each tuple: (compiled regex, friendly message)
_KEYWORD_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"rate.?limit", re.IGNORECASE),
        "Too many requests. Please wait a moment and try again.",
    ),
    (
        re.compile(r"auth|api.?key|credentials?|unauthorized", re.IGNORECASE),
        "A service configuration issue occurred. Please contact support.",
    ),
    (
        re.compile(r"database|sqlite|operational.?error|locked", re.IGNORECASE),
        "A temporary data issue occurred. Please try again in a moment.",
    ),
    (
        re.compile(r"timeout|timed?\s*out", re.IGNORECASE),
        "The request took too long to complete. Please try again.",
    ),
    (
        re.compile(r"connect|refused|unreachable", re.IGNORECASE),
        "Could not connect to the service. Please try again in a moment.",
    ),
]


def sanitize_error(
    exc: Optional[BaseException],
    *,
    context: Optional[str] = None,
) -> str:
    """Return a user-safe error message for *exc*.

    The returned string never contains raw exception text, file paths,
    API keys, or other internal details.

    Args:
        exc: The caught exception (or None).
        context: Optional human-readable description of the operation
            that failed (e.g. ``"processing your image"``).  When
            provided, the message will read
            ``"Sorry, there was an error <context>. <reason>"``

    Returns:
        A sanitized, user-friendly error description.
    """
    if exc is None:
        message = _DEFAULT_MESSAGE
    else:
        message = _resolve_message(exc)

    if context:
        return f"Sorry, there was an error {context}. {message}"

    return message


def _resolve_message(exc: BaseException) -> str:
    """Pick the best user-facing message for *exc*."""
    # 1. Check the type hierarchy (supports subclasses via isinstance)
    for exc_type, msg in _TYPE_MAP.items():
        if isinstance(exc, exc_type):
            return msg

    # 2. Check keyword patterns in the stringified exception
    raw = str(exc)
    for pattern, msg in _KEYWORD_PATTERNS:
        if pattern.search(raw):
            return msg

    # 3. Fallback
    return _DEFAULT_MESSAGE
