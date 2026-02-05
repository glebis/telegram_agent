"""
Tests for the Conversation Archive Service.

Tests cover:
- Writing archive files with correct content and structure
- Listing archives sorted newest first
- Reading specific archive files
- Directory auto-creation
- Edge cases: empty messages, special characters, path traversal prevention
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.conversation_archive import (
    ARCHIVE_BASE_DIR,
    archive_conversation,
    get_archive,
    list_archives,
)


@pytest.fixture
def archive_dir(tmp_path):
    """Override ARCHIVE_BASE_DIR to use tmp_path for test isolation."""
    with patch("src.services.conversation_archive.ARCHIVE_BASE_DIR", tmp_path):
        yield tmp_path


class TestArchiveConversation:
    """Tests for archive_conversation function."""

    def test_creates_archive_file(self, archive_dir):
        """Test that archive_conversation creates a markdown file."""
        messages = [
            {"role": "user", "content": "Hello Claude"},
            {"role": "assistant", "content": "Hello! How can I help?"},
        ]

        path = archive_conversation(
            chat_id=12345, session_id="abc12345-def6-7890", messages=messages
        )

        assert path.exists()
        assert path.suffix == ".md"
        assert path.parent == archive_dir / "12345"

    def test_file_contains_correct_markdown_structure(self, archive_dir):
        """Test that the archive file has proper markdown headers and metadata."""
        messages = [
            {
                "role": "user",
                "content": "What is Python?",
                "timestamp": "2026-02-05T14:00:00",
            },
            {
                "role": "assistant",
                "content": "Python is a programming language.",
                "timestamp": "2026-02-05T14:00:05",
            },
        ]

        path = archive_conversation(
            chat_id=12345, session_id="sess1234-abcd-efgh", messages=messages
        )

        content = path.read_text(encoding="utf-8")

        # Check metadata header
        assert "# Conversation Archive" in content
        assert "**Chat ID**: 12345" in content
        assert "**Session ID**: sess1234-abcd-efgh" in content
        assert "**Messages**: 2" in content

        # Check message sections
        assert "## User" in content
        assert "What is Python?" in content
        assert "## Assistant" in content
        assert "Python is a programming language." in content

        # Check timestamps are included
        assert "2026-02-05T14:00:00" in content
        assert "2026-02-05T14:00:05" in content

    def test_filename_contains_session_prefix(self, archive_dir):
        """Test that filenames contain the session ID prefix."""
        messages = [{"role": "user", "content": "test"}]

        path = archive_conversation(
            chat_id=99, session_id="abcdef12-3456-7890", messages=messages
        )

        # Filename should end with _<first 8 chars of session_id>.md
        assert path.name.endswith("_abcdef12.md")
        # Filename should start with a date pattern
        assert path.name[:10].count("-") == 2  # YYYY-MM-DD

    def test_directory_auto_creation(self, archive_dir):
        """Test that chat directory is created automatically."""
        chat_dir = archive_dir / "54321"
        assert not chat_dir.exists()

        messages = [{"role": "user", "content": "test"}]
        archive_conversation(
            chat_id=54321, session_id="newsession-1234", messages=messages
        )

        assert chat_dir.exists()
        assert chat_dir.is_dir()

    def test_empty_messages_list(self, archive_dir):
        """Test archiving with no messages produces valid file."""
        path = archive_conversation(
            chat_id=12345, session_id="emptysess-1234", messages=[]
        )

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "**Messages**: 0" in content
        assert "*No messages recorded.*" in content

    def test_special_characters_in_content(self, archive_dir):
        """Test that special characters in message content are preserved."""
        messages = [
            {
                "role": "user",
                "content": "Here's some <html> & 'quotes' and \"doubles\"",
            },
            {
                "role": "assistant",
                "content": "```python\nprint('hello')\n```\n\n| col1 | col2 |\n",
            },
        ]

        path = archive_conversation(
            chat_id=12345, session_id="special-chars-1234", messages=messages
        )

        content = path.read_text(encoding="utf-8")
        assert "<html>" in content
        assert "& 'quotes'" in content
        assert "```python\nprint('hello')\n```" in content

    def test_tool_messages_formatted(self, archive_dir):
        """Test that tool messages get the Tool header."""
        messages = [
            {"role": "user", "content": "Read file.py"},
            {"role": "tool", "content": "Read: file.py"},
            {"role": "assistant", "content": "Here's the file content."},
        ]

        path = archive_conversation(
            chat_id=12345, session_id="toolsess-1234", messages=messages
        )

        content = path.read_text(encoding="utf-8")
        assert "## Tool" in content
        assert "Read: file.py" in content

    def test_multiple_archives_dont_overwrite(self, archive_dir):
        """Test that multiple archives for same chat create separate files."""
        messages = [{"role": "user", "content": "first"}]

        path1 = archive_conversation(
            chat_id=12345, session_id="session1-1234", messages=messages
        )

        messages2 = [{"role": "user", "content": "second"}]
        path2 = archive_conversation(
            chat_id=12345, session_id="session2-1234", messages=messages2
        )

        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_returns_path_object(self, archive_dir):
        """Test that the return value is a Path."""
        path = archive_conversation(
            chat_id=12345,
            session_id="pathtest-1234",
            messages=[{"role": "user", "content": "test"}],
        )

        assert isinstance(path, Path)


class TestListArchives:
    """Tests for list_archives function."""

    def test_lists_archives_newest_first(self, archive_dir):
        """Test that archives are listed in reverse chronological order."""
        chat_dir = archive_dir / "12345"
        chat_dir.mkdir(parents=True)

        # Create files with different timestamps
        (chat_dir / "2026-01-01_120000_aaaa1111.md").write_text("old")
        (chat_dir / "2026-02-01_120000_bbbb2222.md").write_text("middle")
        (chat_dir / "2026-03-01_120000_cccc3333.md").write_text("newest")

        archives = list_archives(chat_id=12345)

        assert len(archives) == 3
        assert archives[0].name == "2026-03-01_120000_cccc3333.md"
        assert archives[1].name == "2026-02-01_120000_bbbb2222.md"
        assert archives[2].name == "2026-01-01_120000_aaaa1111.md"

    def test_returns_empty_for_nonexistent_chat(self, archive_dir):
        """Test that listing a non-existent chat returns empty list."""
        archives = list_archives(chat_id=99999)

        assert archives == []

    def test_returns_empty_for_empty_directory(self, archive_dir):
        """Test that listing an empty chat directory returns empty list."""
        chat_dir = archive_dir / "12345"
        chat_dir.mkdir(parents=True)

        archives = list_archives(chat_id=12345)

        assert archives == []

    def test_only_returns_md_files(self, archive_dir):
        """Test that only .md files are listed."""
        chat_dir = archive_dir / "12345"
        chat_dir.mkdir(parents=True)

        (chat_dir / "2026-01-01_120000_aaaa1111.md").write_text("archive")
        (chat_dir / "some_other_file.txt").write_text("not an archive")
        (chat_dir / "notes.json").write_text("{}")

        archives = list_archives(chat_id=12345)

        assert len(archives) == 1
        assert archives[0].name == "2026-01-01_120000_aaaa1111.md"

    def test_returns_path_objects(self, archive_dir):
        """Test that list items are Path objects."""
        chat_dir = archive_dir / "12345"
        chat_dir.mkdir(parents=True)
        (chat_dir / "2026-01-01_120000_aaaa1111.md").write_text("test")

        archives = list_archives(chat_id=12345)

        assert all(isinstance(p, Path) for p in archives)


class TestGetArchive:
    """Tests for get_archive function."""

    def test_reads_existing_archive(self, archive_dir):
        """Test reading an existing archive file."""
        chat_dir = archive_dir / "12345"
        chat_dir.mkdir(parents=True)
        expected = "# Test Archive Content\n\nHello world."
        (chat_dir / "2026-01-01_120000_aaaa1111.md").write_text(
            expected, encoding="utf-8"
        )

        content = get_archive(chat_id=12345, filename="2026-01-01_120000_aaaa1111.md")

        assert content == expected

    def test_returns_none_for_missing_file(self, archive_dir):
        """Test that missing files return None."""
        chat_dir = archive_dir / "12345"
        chat_dir.mkdir(parents=True)

        content = get_archive(chat_id=12345, filename="nonexistent.md")

        assert content is None

    def test_returns_none_for_missing_chat_dir(self, archive_dir):
        """Test that missing chat directory returns None."""
        content = get_archive(chat_id=99999, filename="2026-01-01_120000_aaaa1111.md")

        assert content is None

    def test_blocks_path_traversal(self, archive_dir):
        """Test that path traversal attempts are blocked."""
        chat_dir = archive_dir / "12345"
        chat_dir.mkdir(parents=True)
        (chat_dir / "legit.md").write_text("legit")

        # Try to escape the chat directory
        content = get_archive(chat_id=12345, filename="../../../etc/passwd")

        assert content is None

    def test_blocks_absolute_path_in_filename(self, archive_dir):
        """Test that absolute paths in filename are blocked."""
        content = get_archive(chat_id=12345, filename="/etc/passwd")

        assert content is None


class TestRoundTrip:
    """Integration tests: archive then read back."""

    def test_archive_and_read_back(self, archive_dir):
        """Test writing an archive and reading it back."""
        messages = [
            {"role": "user", "content": "Tell me about Python"},
            {"role": "assistant", "content": "Python is great!"},
        ]

        path = archive_conversation(
            chat_id=12345, session_id="roundtrip-1234-5678", messages=messages
        )

        content = get_archive(chat_id=12345, filename=path.name)

        assert content is not None
        assert "Tell me about Python" in content
        assert "Python is great!" in content

    def test_archive_and_list(self, archive_dir):
        """Test writing archives and listing them."""
        # Use session IDs that differ in the first 8 chars to avoid
        # filename collisions when all run within the same second
        session_ids = ["aaaabbbb-1234", "ccccdddd-1234", "eeeeffff-1234"]
        for i, sid in enumerate(session_ids):
            archive_conversation(
                chat_id=12345,
                session_id=sid,
                messages=[{"role": "user", "content": f"message {i}"}],
            )

        archives = list_archives(chat_id=12345)

        assert len(archives) == 3
