"""
Tests that handler files use sanitize_error() instead of str(e) in user messages.

Covers srs_handlers.py, poll_handlers.py, note_commands.py, claude_commands.py,
message_handlers.py, and processor files.
"""

from pathlib import Path

import pytest

# Base path for the source tree
_SRC = Path(__file__).resolve().parent.parent.parent / "src"


def _read(rel_path: str) -> str:
    """Read a source file relative to src/."""
    return (_SRC / rel_path).read_text()


def _find_str_e_in_user_messages(source: str) -> list[tuple[int, str]]:
    """Find lines where str(e) appears in user-facing message calls.

    Returns list of (line_number, stripped_line) tuples.
    Checks both same-line and multi-line patterns.
    """
    hits = []
    lines = source.splitlines()
    call_keywords = (
        "reply_text",
        "send_message_sync",
        "edit_message_sync",
        "edit_text",
        "send_message",
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("logger.") or stripped.startswith("#"):
            continue
        if "str(e)" not in stripped:
            continue

        # Same-line check
        if any(kw in line for kw in call_keywords):
            hits.append((i + 1, stripped))
            continue

        # Multi-line: look back up to 5 lines for a user-facing call
        for back in range(1, 6):
            if i - back < 0:
                break
            prev = lines[i - back].strip()
            if prev.startswith("logger.") or prev.startswith("#"):
                continue
            if any(kw in prev for kw in call_keywords):
                hits.append((i + 1, stripped))
                break

    return hits


class TestSrsHandlersNoStrE:
    """Verify srs_handlers.py does not leak str(e)."""

    def test_no_str_e_in_user_messages(self):
        source = _read("bot/handlers/srs_handlers.py")
        hits = _find_str_e_in_user_messages(source)
        assert hits == [], (
            f"srs_handlers.py has str(e) in user messages at lines: "
            f"{[ln for ln, _ in hits]}"
        )

    def test_imports_sanitize_error(self):
        source = _read("bot/handlers/srs_handlers.py")
        assert "sanitize_error" in source


class TestPollHandlersNoStrE:
    """Verify poll_handlers.py does not leak str(e)."""

    def test_no_str_e_in_user_messages(self):
        source = _read("bot/handlers/poll_handlers.py")
        hits = _find_str_e_in_user_messages(source)
        assert hits == [], (
            f"poll_handlers.py has str(e) in user messages at lines: "
            f"{[ln for ln, _ in hits]}"
        )


class TestNoteCommandsNoStrE:
    """Verify note_commands.py does not leak str(e)."""

    def test_no_str_e_in_user_messages(self):
        source = _read("bot/handlers/note_commands.py")
        hits = _find_str_e_in_user_messages(source)
        assert hits == [], (
            f"note_commands.py has str(e) in user messages at lines: "
            f"{[ln for ln, _ in hits]}"
        )


class TestClaudeCommandsNoStrE:
    """Verify claude_commands.py does not leak str(e)."""

    def test_no_str_e_in_user_messages(self):
        source = _read("bot/handlers/claude_commands.py")
        hits = _find_str_e_in_user_messages(source)
        assert hits == [], (
            f"claude_commands.py has str(e) in user messages at lines: "
            f"{[ln for ln, _ in hits]}"
        )


class TestMessageHandlersNoStrE:
    """Verify message_handlers.py does not leak str(e)."""

    def test_no_str_e_in_user_messages(self):
        source = _read("bot/message_handlers.py")
        hits = _find_str_e_in_user_messages(source)
        assert hits == [], (
            f"message_handlers.py has str(e) in user messages at lines: "
            f"{[ln for ln, _ in hits]}"
        )


class TestProcessorFilesNoStrE:
    """Verify processor files do not leak str(e)."""

    @pytest.mark.parametrize(
        "rel_path",
        [
            "bot/processors/text.py",
            "bot/processors/media.py",
            "bot/processors/content.py",
            "bot/processors/router.py",
            "bot/processors/collect.py",
        ],
    )
    def test_no_str_e_in_user_messages(self, rel_path):
        source = _read(rel_path)
        hits = _find_str_e_in_user_messages(source)
        assert hits == [], (
            f"{rel_path} has str(e) in user messages at lines: "
            f"{[ln for ln, _ in hits]}"
        )
