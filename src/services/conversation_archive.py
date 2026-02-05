"""
Conversation Archive Service

Archives Claude Code session transcripts to disk as timestamped markdown files.
Files are saved to data/conversations/<chat_id>/<timestamp>_<session_id>.md

This is append-only: old archives are never overwritten or deleted.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Base directory for conversation archives (relative to project root)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
ARCHIVE_BASE_DIR = _PROJECT_ROOT / "data" / "conversations"


def _get_chat_dir(chat_id: int) -> Path:
    """Get the archive directory for a specific chat."""
    return ARCHIVE_BASE_DIR / str(chat_id)


def _format_message(msg: dict) -> str:
    """Format a single message dict as a markdown section.

    Expected keys:
        - role: "user", "assistant", or "tool"
        - content: The text content
        - timestamp: Optional ISO timestamp string
    """
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    timestamp = msg.get("timestamp", "")

    if role == "user":
        header = "## User"
    elif role == "assistant":
        header = "## Assistant"
    elif role == "tool":
        header = "## Tool"
    else:
        header = f"## {role.capitalize()}"

    if timestamp:
        header += f"  \n*{timestamp}*"

    return f"{header}\n\n{content}\n"


def archive_conversation(
    chat_id: int,
    session_id: str,
    messages: list[dict],
) -> Path:
    """Archive a conversation transcript to disk.

    Saves the conversation as a timestamped markdown file in
    data/conversations/<chat_id>/<timestamp>_<session_id>.md

    Args:
        chat_id: Telegram chat ID
        session_id: Claude session ID
        messages: List of message dicts with keys: role, content, timestamp (optional)

    Returns:
        Path to the saved archive file
    """
    chat_dir = _get_chat_dir(chat_id)
    chat_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    short_id = session_id[:8] if session_id else "unknown"
    filename = f"{timestamp}_{short_id}.md"
    filepath = chat_dir / filename

    # Build markdown content
    lines = [
        f"# Conversation Archive",
        f"",
        f"- **Chat ID**: {chat_id}",
        f"- **Session ID**: {session_id}",
        f"- **Archived**: {datetime.utcnow().isoformat()}Z",
        f"- **Messages**: {len(messages)}",
        f"",
        f"---",
        f"",
    ]

    if not messages:
        lines.append("*No messages recorded.*\n")
    else:
        for msg in messages:
            lines.append(_format_message(msg))

    content = "\n".join(lines)

    filepath.write_text(content, encoding="utf-8")
    logger.info(
        f"Archived conversation for chat {chat_id}, "
        f"session {short_id}, {len(messages)} messages -> {filepath}"
    )

    return filepath


def list_archives(chat_id: int) -> list[Path]:
    """List archived conversations for a chat, newest first.

    Args:
        chat_id: Telegram chat ID

    Returns:
        List of Path objects for archive files, sorted newest first
    """
    chat_dir = _get_chat_dir(chat_id)

    if not chat_dir.exists():
        return []

    archives = sorted(chat_dir.glob("*.md"), reverse=True)
    return archives


def get_archive(chat_id: int, filename: str) -> Optional[str]:
    """Read a specific archive file.

    Args:
        chat_id: Telegram chat ID
        filename: Name of the archive file (e.g., "2026-02-05_143022_abcd1234.md")

    Returns:
        File contents as string, or None if not found
    """
    chat_dir = _get_chat_dir(chat_id)
    filepath = chat_dir / filename

    # Prevent path traversal
    try:
        filepath = filepath.resolve()
        if not filepath.is_relative_to(chat_dir.resolve()):
            logger.warning(
                f"Path traversal attempt blocked: {filename} for chat {chat_id}"
            )
            return None
    except (ValueError, OSError):
        return None

    if not filepath.exists():
        return None

    return filepath.read_text(encoding="utf-8")
