"""
Per-chat workspace service.

Manages per-chat CLAUDE.md memory files that persist user preferences
and context across Claude Code sessions.

Storage: data/workspaces/<chat_id>/CLAUDE.md
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Base directory for all chat workspaces
WORKSPACES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "workspaces"

DEFAULT_TEMPLATE = """# Chat Memory

## Preferences

## Context
"""


def _workspace_dir(chat_id: int) -> Path:
    """Return the workspace directory for a chat, with path traversal protection."""
    safe_id = str(int(chat_id))  # Force int conversion to prevent injection
    return WORKSPACES_DIR / safe_id


def ensure_workspace(chat_id: int) -> Path:
    """Create workspace directory and CLAUDE.md from template if missing.

    Returns the path to the workspace directory.
    """
    ws_dir = _workspace_dir(chat_id)
    ws_dir.mkdir(parents=True, exist_ok=True)

    memory_file = ws_dir / "CLAUDE.md"
    if not memory_file.exists():
        memory_file.write_text(DEFAULT_TEMPLATE, encoding="utf-8")
        logger.info("Created workspace with default CLAUDE.md for chat %s", chat_id)

    return ws_dir


def get_memory(chat_id: int) -> str | None:
    """Read CLAUDE.md content for a chat.

    Returns None if the workspace or file doesn't exist.
    """
    memory_file = _workspace_dir(chat_id) / "CLAUDE.md"
    if not memory_file.exists():
        return None
    return memory_file.read_text(encoding="utf-8")


def update_memory(chat_id: int, content: str) -> None:
    """Overwrite CLAUDE.md with new content."""
    ws_dir = ensure_workspace(chat_id)
    (ws_dir / "CLAUDE.md").write_text(content, encoding="utf-8")
    logger.info("Updated memory for chat %s (%d chars)", chat_id, len(content))


def append_memory(chat_id: int, content: str) -> None:
    """Append text to CLAUDE.md."""
    ws_dir = ensure_workspace(chat_id)
    memory_file = ws_dir / "CLAUDE.md"
    existing = memory_file.read_text(encoding="utf-8")
    memory_file.write_text(existing + "\n" + content, encoding="utf-8")
    logger.info("Appended %d chars to memory for chat %s", len(content), chat_id)


def reset_memory(chat_id: int) -> None:
    """Restore CLAUDE.md to the default template."""
    ws_dir = ensure_workspace(chat_id)
    (ws_dir / "CLAUDE.md").write_text(DEFAULT_TEMPLATE, encoding="utf-8")
    logger.info("Reset memory to default template for chat %s", chat_id)


def export_memory_path(chat_id: int) -> Path | None:
    """Return the CLAUDE.md file path if it exists, for sending as a document."""
    memory_file = _workspace_dir(chat_id) / "CLAUDE.md"
    if memory_file.exists():
        return memory_file
    return None
