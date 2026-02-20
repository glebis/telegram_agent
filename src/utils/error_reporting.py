"""Standardized error reporting for bot handlers.

Provides:
- ErrorCategory enum for classifying exceptions
- classify_error() to map exceptions to categories
- ErrorCounter for tracking error counts by category
- format_user_error_message() for user-friendly messages
- handle_errors() decorator for wrapping async handler functions
"""

import functools
import logging
from enum import Enum
from typing import Dict, Optional

from .telegram_api import send_message_sync

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories for classifying handler errors."""

    NETWORK = "network"
    DATABASE = "database"
    VALIDATION = "validation"
    AUTH = "auth"
    API = "api"
    INTERNAL = "internal"


def classify_error(exc: Exception) -> ErrorCategory:
    """Classify an exception into an error category."""
    # Auth errors (PermissionError before OSError — it's a subclass)
    if isinstance(exc, PermissionError):
        return ErrorCategory.AUTH

    # Network errors
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return ErrorCategory.NETWORK

    # Database errors (check module name for SQLAlchemy)
    module = getattr(type(exc), "__module__", "") or ""
    if "sqlalchemy" in module:
        return ErrorCategory.DATABASE

    # Validation errors
    if isinstance(exc, (ValueError, TypeError, KeyError, IndexError)):
        return ErrorCategory.VALIDATION

    return ErrorCategory.INTERNAL


class ErrorCounter:
    """In-memory counter for errors by category."""

    def __init__(self) -> None:
        self._counts: Dict[ErrorCategory, int] = {cat: 0 for cat in ErrorCategory}

    def increment(self, category: ErrorCategory) -> None:
        """Increment the count for a category."""
        self._counts[category] = self._counts.get(category, 0) + 1

    def get_counts(self) -> Dict[ErrorCategory, int]:
        """Return a copy of all counts."""
        return dict(self._counts)

    def get_total(self) -> int:
        """Return total errors across all categories."""
        return sum(self._counts.values())

    def reset(self) -> None:
        """Reset all counts to zero."""
        for cat in ErrorCategory:
            self._counts[cat] = 0


# Global singleton
_error_counter: Optional[ErrorCounter] = None


def get_error_counter() -> ErrorCounter:
    """Get the global error counter singleton."""
    global _error_counter
    if _error_counter is None:
        _error_counter = ErrorCounter()
    return _error_counter


_USER_MESSAGES = {
    ErrorCategory.NETWORK: (
        "A network connection error occurred. Please try again in a moment."
    ),
    ErrorCategory.DATABASE: (
        "A database/storage error occurred. Please try again shortly."
    ),
    ErrorCategory.VALIDATION: (
        "The input appears to be invalid. Please check and try again."
    ),
    ErrorCategory.AUTH: "You don't have permission to perform this action.",
    ErrorCategory.API: ("An external service error occurred. Please try again later."),
    ErrorCategory.INTERNAL: ("An unexpected error occurred. Please try again later."),
}


def format_user_error_message(category: ErrorCategory, handler_name: str) -> str:
    """Format a user-friendly error message for a category."""
    return _USER_MESSAGES.get(category, _USER_MESSAGES[ErrorCategory.INTERNAL])


def handle_errors(handler_name: str):
    """Decorator that wraps async handlers with standardized error handling.

    Catches exceptions, classifies them, logs structured context,
    increments the global error counter, and sends a user-friendly
    message via Telegram.

    Usage:
        @handle_errors("my_command")
        async def my_command(update, context):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            try:
                return await func(update, context, *args, **kwargs)
            except Exception as exc:
                category = classify_error(exc)
                get_error_counter().increment(category)

                # Structured log
                chat_id = None
                user_id = None
                if update and getattr(update, "effective_chat", None):
                    chat_id = update.effective_chat.id
                if update and getattr(update, "effective_user", None):
                    user_id = update.effective_user.id

                logger.error(
                    "Handler '%s' error [%s]: %s " "(chat_id=%s, user_id=%s)",
                    handler_name,
                    category.value,
                    exc,
                    chat_id,
                    user_id,
                    exc_info=True,
                )

                # Send user-friendly message
                if chat_id is not None:
                    msg = format_user_error_message(category, handler_name)
                    try:
                        send_message_sync(
                            chat_id=chat_id,
                            text=msg,
                        )
                    except Exception:
                        logger.debug(
                            "Failed to send error message to chat %s",
                            chat_id,
                        )

        return wrapper

    return decorator
