"""
Life Weeks Reply Handler — Routes reflections to vault notes.

When users reply to weekly Life Weeks notifications, this handler
saves their reflections to the configured vault location.
"""

import logging
from datetime import datetime
from pathlib import Path

from .reply_context import ReplyContext

logger = logging.getLogger(__name__)


async def handle_life_weeks_reply(
    user_id: int,
    reply_text: str,
    context: ReplyContext,
) -> Path:
    """
    Route life weeks reflection to configured vault location.

    Args:
        user_id: Telegram user ID
        reply_text: User's reflection text
        context: Reply context with routing metadata

    Returns:
        Path to the file where reflection was appended

    Raises:
        ValueError: If destination is invalid or path cannot be determined
    """
    destination = context.life_weeks_reply_destination or "daily_note"
    weeks_lived = context.weeks_lived or 0

    logger.info(f"Routing life weeks reflection for user {user_id} to {destination}")

    if destination == "daily_note":
        path = _append_to_daily_note(reply_text, weeks_lived)
    elif destination == "weekly_note":
        path = _append_to_weekly_note(reply_text, weeks_lived)
    elif destination == "custom_journal":
        custom_path = context.life_weeks_custom_path
        if not custom_path:
            custom_path = "~/Research/vault/Journal/life-reflections.md"
        path = _append_to_custom_journal(reply_text, weeks_lived, custom_path)
    else:
        raise ValueError(f"Unknown destination: {destination}")

    logger.info(f"Saved life weeks reflection to {path}")
    return path


def _append_to_daily_note(reply_text: str, weeks_lived: int) -> Path:
    """Append reflection to today's daily note."""
    today = datetime.now().strftime("%Y%m%d")
    vault_path = Path.home() / "Research" / "vault" / "Daily"
    note_path = vault_path / f"{today}.md"

    section_header = "## Life Reflection"
    entry = _format_reflection_entry(reply_text, weeks_lived)

    _append_to_note(note_path, section_header, entry, create_if_missing=True)

    return note_path


def _append_to_weekly_note(reply_text: str, weeks_lived: int) -> Path:
    """Append reflection to this week's weekly note (YYYYMM format)."""
    # Weekly note format is YYYYMM (e.g., 202602 for February 2026)
    year_month = datetime.now().strftime("%Y%m")
    vault_path = Path.home() / "Research" / "vault" / "Weekly"
    note_path = vault_path / f"{year_month}.md"

    section_header = "## Life Reflections"
    entry = _format_reflection_entry(reply_text, weeks_lived)

    _append_to_note(note_path, section_header, entry, create_if_missing=True)

    return note_path


def _append_to_custom_journal(
    reply_text: str, weeks_lived: int, custom_path: str
) -> Path:
    """Append reflection to custom journal path."""
    note_path = Path(custom_path).expanduser()

    section_header = f"## Week {weeks_lived}"
    entry = _format_reflection_entry(reply_text, weeks_lived, include_week=False)

    _append_to_note(note_path, section_header, entry, create_if_missing=True)

    return note_path


def _format_reflection_entry(
    reply_text: str, weeks_lived: int, include_week: bool = True
) -> str:
    """Format reflection entry with timestamp and optional week number."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if include_week:
        return f"**Week {weeks_lived}** ({timestamp})\n{reply_text}\n"
    else:
        return f"({timestamp})\n{reply_text}\n"


def _append_to_note(
    note_path: Path,
    section_header: str,
    entry: str,
    create_if_missing: bool = False,
) -> None:
    """
    Append entry to a note under the specified section.

    If the section doesn't exist, it will be created.
    If the note doesn't exist and create_if_missing is True, it will be created.

    Args:
        note_path: Path to the note file
        section_header: Markdown section header (e.g., "## Life Reflection")
        entry: Text to append under the section
        create_if_missing: If True, create note if it doesn't exist
    """
    # Ensure parent directory exists
    note_path.parent.mkdir(parents=True, exist_ok=True)

    if not note_path.exists():
        if create_if_missing:
            _create_note_with_section(note_path, section_header, entry)
            logger.info(f"Created new note: {note_path}")
        else:
            raise FileNotFoundError(f"Note not found: {note_path}")
        return

    # Read existing content
    content = note_path.read_text()

    # Check if section exists
    if section_header in content:
        # Find section and append after it
        lines = content.split("\n")
        section_line_idx = next(
            (i for i, line in enumerate(lines) if line.startswith(section_header)),
            None,
        )

        if section_line_idx is not None:
            # Find the next section or end of file
            next_section_idx = None
            for i in range(section_line_idx + 1, len(lines)):
                if lines[i].startswith("##"):
                    next_section_idx = i
                    break

            # Insert entry before next section or at end
            insert_idx = next_section_idx if next_section_idx else len(lines)
            lines.insert(insert_idx, entry)

            new_content = "\n".join(lines)
            note_path.write_text(new_content)
            logger.debug(f"Appended to existing section in {note_path}")
    else:
        # Section doesn't exist, append at end
        new_content = content.rstrip() + f"\n\n{section_header}\n{entry}"
        note_path.write_text(new_content)
        logger.debug(f"Created new section in {note_path}")


def _create_note_with_section(note_path: Path, section_header: str, entry: str) -> None:
    """Create a new note with basic structure and the first entry."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Basic frontmatter
    content = f"""---
created: {today}
---

# {note_path.stem}

{section_header}
{entry}
"""

    note_path.write_text(content)


def get_obsidian_uri(note_path: Path) -> str:
    """
    Generate Obsidian deep link URI for a note path.

    Args:
        note_path: Absolute path to the note

    Returns:
        obsidian:// URI that opens the note in Obsidian
    """
    # Get relative path from vault root
    vault_root = Path.home() / "Research" / "vault"

    try:
        relative_path = note_path.relative_to(vault_root)
        # URL encode the path
        from urllib.parse import quote

        encoded_path = quote(str(relative_path))

        # Obsidian URI format: obsidian://open?vault=VaultName&file=Path/To/Note.md
        # Note: vault name is "vault" (the folder name)
        return f"obsidian://open?vault=vault&file={encoded_path}"
    except ValueError:
        # Path is not relative to vault root
        logger.warning(f"Note path {note_path} is not in vault, cannot create URI")
        return str(note_path)
