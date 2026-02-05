"""
Hierarchical authorization model for the Telegram agent.

Defines four tiers of access (descending privilege):
    OWNER  - Bot owner, unrestricted access
    ADMIN  - Trusted administrators, full tool access
    USER   - Authenticated users, safe tool subset
    GROUP  - Group/supergroup members, read-only tools

Backward compatible: when OWNER_USER_ID is not set, all authenticated
users are treated as OWNER (single-user default).
"""

import enum
import functools
import logging
from typing import Callable, List, Optional

from .config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth tier enum
# ---------------------------------------------------------------------------


class AuthTier(enum.IntEnum):
    """Authorization tiers, higher value = more privilege."""

    GROUP = 0
    USER = 1
    ADMIN = 2
    OWNER = 3


# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------


def _parse_id_list(raw: str) -> set[int]:
    """Parse a comma-separated string of integer IDs into a set."""
    result: set[int] = set()
    if not raw or not raw.strip():
        return result
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result


def get_user_tier(user_id: int, chat_id: int) -> AuthTier:
    """
    Resolve the authorization tier for a user in a given chat.

    Resolution order (first match wins):
    1. OWNER if user_id == settings.owner_user_id
    2. ADMIN if user_id in settings.admin_user_ids
    3. USER  if user_id in settings.allowed_user_ids (or allowlist empty)
    4. GROUP for group/supergroup chats (negative chat_id)

    Backward compatible: if owner_user_id is not set, all users are OWNER.
    """
    settings = get_settings()

    # Backward compatibility: no owner configured => everyone is OWNER
    if not settings.owner_user_id:
        return AuthTier.OWNER

    # 1. Owner check
    if user_id == settings.owner_user_id:
        return AuthTier.OWNER

    # 2. Admin check
    admin_ids = _parse_id_list(settings.admin_user_ids)
    if user_id in admin_ids:
        return AuthTier.ADMIN

    # 3. User allowlist check
    allowed_ids = _parse_id_list(settings.allowed_user_ids)
    if not allowed_ids:
        # Empty allowlist: all authenticated users are USER in private chats
        if chat_id >= 0:
            return AuthTier.USER
    elif user_id in allowed_ids:
        return AuthTier.USER

    # 4. Group/supergroup chats (negative chat_id) default to GROUP
    if chat_id < 0:
        return AuthTier.GROUP

    # Private chat but not in any list => GROUP
    return AuthTier.GROUP


# ---------------------------------------------------------------------------
# @require_tier decorator
# ---------------------------------------------------------------------------


def require_tier(minimum_tier: AuthTier) -> Callable:
    """
    Decorator that restricts a command handler to users at or above the
    specified tier.

    Usage::

        @require_tier(AuthTier.ADMIN)
        async def settings_command(update, context):
            ...

    If the user's tier is below *minimum_tier*, sends a polite denial
    message and returns without calling the handler.

    Works with python-telegram-bot handler signature ``(update, context)``.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user = getattr(update, "effective_user", None)
            chat = getattr(update, "effective_chat", None)

            if user is None or chat is None:
                return

            tier = get_user_tier(user.id, chat.id)

            if tier >= minimum_tier:
                return await func(update, context, *args, **kwargs)

            # Insufficient tier - send polite denial
            logger.info(
                "Authorization denied: user %d tier %s < required %s for %s",
                user.id,
                tier.name,
                minimum_tier.name,
                func.__name__,
            )

            message = getattr(update, "message", None)
            if message is not None:
                await message.reply_text("You are not authorized to use this command.")

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Per-tier Claude tool restrictions
# ---------------------------------------------------------------------------

# Safe tools for USER tier (no shell/Bash execution)
_USER_TOOLS: List[str] = ["Read", "Glob", "Grep", "Write", "Edit"]

# Read-only tools for GROUP tier
_GROUP_TOOLS: List[str] = ["Read", "Glob", "Grep"]


def get_allowed_tools_for_tier(tier: AuthTier) -> Optional[List[str]]:
    """
    Return the list of Claude tools allowed for a given tier.

    Returns:
        None  - unrestricted (OWNER, ADMIN)
        list  - restricted tool set (USER, GROUP)
    """
    if tier >= AuthTier.ADMIN:
        return None  # Unrestricted
    if tier == AuthTier.USER:
        return list(_USER_TOOLS)
    # GROUP or below
    return list(_GROUP_TOOLS)
