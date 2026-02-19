"""Tests that note_commands uses async subprocess instead of blocking subprocess.run."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update."""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Create a mock Telegram context."""
    return MagicMock()


@pytest.mark.asyncio
async def test_view_note_does_not_call_blocking_subprocess(
    mock_update, mock_context, tmp_path
):
    """view_note_command must NOT call subprocess.run (blocks event loop)."""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    settings_mock = MagicMock()
    settings_mock.vault_path = str(vault_path)

    with (
        patch(
            "src.bot.handlers.note_commands.get_settings",
            return_value=settings_mock,
        ),
        patch(
            "src.bot.handlers.note_commands.get_user_locale_from_update",
            return_value="en",
        ),
        patch("src.bot.handlers.note_commands.t", return_value="Not found"),
        patch("subprocess.run") as mock_subprocess_run,
    ):
        # Note doesn't exist at direct path, triggers recursive search
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 1

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_process,
        ):
            from src.bot.handlers.note_commands import view_note_command

            await view_note_command(mock_update, mock_context, "nonexistent")

        # subprocess.run must NOT have been called
        mock_subprocess_run.assert_not_called()


@pytest.mark.asyncio
async def test_view_note_uses_async_subprocess_for_find(
    mock_update, mock_context, tmp_path
):
    """view_note_command must use asyncio.create_subprocess_exec for find."""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    settings_mock = MagicMock()
    settings_mock.vault_path = str(vault_path)

    with (
        patch(
            "src.bot.handlers.note_commands.get_settings",
            return_value=settings_mock,
        ),
        patch(
            "src.bot.handlers.note_commands.get_user_locale_from_update",
            return_value="en",
        ),
        patch("src.bot.handlers.note_commands.t", return_value="Not found"),
    ):
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 1

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_process,
        ) as mock_async_exec:
            from src.bot.handlers.note_commands import view_note_command

            await view_note_command(mock_update, mock_context, "nonexistent")

            mock_async_exec.assert_called()
            find_calls = [c for c in mock_async_exec.call_args_list if "find" in str(c)]
            assert (
                len(find_calls) >= 1
            ), "Expected asyncio.create_subprocess_exec to be called with find"


@pytest.mark.asyncio
async def test_view_note_async_find_returns_match(mock_update, mock_context, tmp_path):
    """view_note_command uses async find and correctly reads a found note."""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    subdir = vault_path / "subfolder"
    subdir.mkdir()
    note_file = subdir / "mynote.md"
    note_file.write_text("# Hello World\nSome content here.")

    settings_mock = MagicMock()
    settings_mock.vault_path = str(vault_path)

    with (
        patch(
            "src.bot.handlers.note_commands.get_settings",
            return_value=settings_mock,
        ),
        patch(
            "src.bot.handlers.note_commands.get_user_locale_from_update",
            return_value="en",
        ),
        patch("src.bot.handlers.note_commands.t", return_value="test"),
    ):
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(str(note_file).encode() + b"\n", b"")
        )
        mock_process.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_process,
        ):
            from src.bot.handlers.note_commands import view_note_command

            await view_note_command(mock_update, mock_context, "mynote")

            # Should have replied with note content, not an error
            reply_calls = mock_update.message.reply_text.call_args_list
            # At least one call should contain "Hello World" (the note content)
            content_replies = [c for c in reply_calls if "Hello World" in str(c)]
            assert (
                len(content_replies) >= 1
            ), f"Expected reply with note content, got: {reply_calls}"
