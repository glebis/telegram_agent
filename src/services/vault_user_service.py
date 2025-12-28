"""
Vault User Service

Looks up Telegram users in Obsidian vault People folder
to provide rich context in Claude prompts.
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from ..core.config import get_settings

logger = logging.getLogger(__name__)


def _get_vault_people_path() -> Path:
    """Get vault People directory from config."""
    return Path(get_settings().vault_people_dir).expanduser()


# Keep for backwards compatibility, but prefer _get_vault_people_path()
VAULT_PEOPLE_PATH = Path.home() / "Research" / "vault" / "People"

# Simple cache: {handle: (note_name, timestamp)}
_user_cache: Dict[str, tuple[Optional[str], datetime]] = {}
CACHE_TTL_MINUTES = 30


def _normalize_handle(handle: str) -> str:
    """Normalize telegram handle (lowercase, strip @)."""
    return handle.lower().lstrip("@")


def _extract_handle_from_yaml(telegram_value: str) -> Optional[str]:
    """
    Extract handle from various YAML formats:
    - "@AndrewKislov"
    - '@IvanDrobyshev'
    - [@alex_named](https://t.me/@alex_named)
    - ""
    """
    if not telegram_value or telegram_value in ('""', "''"):
        return None

    # Strip quotes
    value = telegram_value.strip().strip('"').strip("'")
    if not value:
        return None

    # Check for markdown link format: [@handle](url)
    md_match = re.match(r"\[@?([^\]]+)\]", value)
    if md_match:
        return md_match.group(1)

    # Plain handle with optional @
    return value.lstrip("@")


def _parse_frontmatter(content: str) -> Dict[str, str]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}

    end_idx = content.find("---", 3)
    if end_idx == -1:
        return {}

    yaml_content = content[3:end_idx]
    result = {}

    for line in yaml_content.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()

    return result


def lookup_telegram_user(telegram_handle: str) -> Optional[str]:
    """
    Search People/ folder for a note with matching telegram field.

    Args:
        telegram_handle: Telegram username (with or without @)

    Returns:
        Note name (e.g., "Andrew Kislov") for wikilink, or None if not found
    """
    if not telegram_handle:
        return None

    normalized = _normalize_handle(telegram_handle)

    # Check cache
    if normalized in _user_cache:
        cached_name, timestamp = _user_cache[normalized]
        if datetime.now() - timestamp < timedelta(minutes=CACHE_TTL_MINUTES):
            return cached_name

    # Scan People folder
    people_path = _get_vault_people_path()
    if not people_path.exists():
        logger.warning(f"Vault People path does not exist: {people_path}")
        return None

    for note_path in people_path.glob("@*.md"):
        try:
            content = note_path.read_text(encoding="utf-8")
            frontmatter = _parse_frontmatter(content)

            telegram_value = frontmatter.get("telegram", "")
            note_handle = _extract_handle_from_yaml(telegram_value)

            if note_handle and _normalize_handle(note_handle) == normalized:
                # Extract note name (remove @ prefix and .md suffix)
                note_name = note_path.stem.lstrip("@")
                _user_cache[normalized] = (note_name, datetime.now())
                logger.info(f"Found vault note for @{telegram_handle}: {note_name}")
                return note_name

        except Exception as e:
            logger.warning(f"Error reading {note_path}: {e}")
            continue

    # Not found - cache negative result
    _user_cache[normalized] = (None, datetime.now())
    return None


def build_forward_context(forward_info: dict) -> Optional[str]:
    """
    Build context string for a forwarded message.

    Args:
        forward_info: Dict with forward_from_username, forward_from_first_name,
                     forward_sender_name, forward_from_chat_title

    Returns:
        Context string like:
        - "Message forwarded from [[@Andrew Kislov]]:"
        - "Message forwarded from @some_user:"
        - "Message forwarded from John Doe:"
        - "Message forwarded from channel \"Some Channel\":"
    """
    # Try username first (most identifiable)
    if forward_info.get("forward_from_username"):
        handle = forward_info["forward_from_username"]
        note_name = lookup_telegram_user(handle)
        if note_name:
            return f"Message forwarded from [[@{note_name}]]:"
        else:
            return f"Message forwarded from @{handle}:"

    # Privacy-protected forward (only name available)
    if forward_info.get("forward_sender_name"):
        name = forward_info["forward_sender_name"]
        return f"Message forwarded from {name}:"

    # Channel/group forward
    if forward_info.get("forward_from_chat_title"):
        title = forward_info["forward_from_chat_title"]
        chat_username = forward_info.get("forward_from_chat_username")
        message_id = forward_info.get("forward_message_id")
        if chat_username and message_id:
            url = f"https://t.me/{chat_username}/{message_id}"
            return f'Message forwarded from channel "{title}" ({url}):'
        return f'Message forwarded from channel "{title}":'

    # User with no username (use first name)
    first_name = forward_info.get("forward_from_first_name", "")
    if first_name:
        return f"Message forwarded from {first_name}:"

    return None
