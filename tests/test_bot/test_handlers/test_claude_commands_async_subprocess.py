"""Tests that claude_commands uses async subprocess instead of blocking subprocess.run."""

import asyncio
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


def _patch_claude_reset_deps():
    """Return context managers for all _claude_reset dependencies."""
    service = MagicMock()
    service.end_session = AsyncMock(return_value=True)

    return (
        patch(
            "src.services.claude_code_service.get_claude_code_service",
            return_value=service,
        ),
        patch(
            "src.bot.handlers.claude_commands.set_claude_mode",
            new_callable=AsyncMock,
        ),
        patch(
            "src.bot.handlers.claude_commands.get_user_locale_from_update",
            return_value="en",
        ),
        patch("src.bot.handlers.claude_commands.t", return_value="test"),
    )


@pytest.mark.asyncio
async def test_claude_reset_does_not_call_blocking_subprocess(
    mock_update, mock_context
):
    """_claude_reset must NOT call subprocess.run (blocks event loop)."""
    p1, p2, p3, p4 = _patch_claude_reset_deps()
    with p1, p2, p3, p4, patch("subprocess.run") as mock_subprocess_run:
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 1

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_process,
        ):
            from src.bot.handlers.claude_commands import _claude_reset

            await _claude_reset(mock_update, mock_context)

        # subprocess.run must NOT have been called
        mock_subprocess_run.assert_not_called()


@pytest.mark.asyncio
async def test_claude_reset_uses_async_subprocess_for_pgrep(
    mock_update, mock_context
):
    """_claude_reset must use asyncio.create_subprocess_exec for pgrep."""
    p1, p2, p3, p4 = _patch_claude_reset_deps()
    with p1, p2, p3, p4:
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 1

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_process,
        ) as mock_async_exec:
            from src.bot.handlers.claude_commands import _claude_reset

            await _claude_reset(mock_update, mock_context)

            mock_async_exec.assert_called()
            pgrep_calls = [
                c for c in mock_async_exec.call_args_list if "pgrep" in str(c)
            ]
            assert len(pgrep_calls) >= 1, (
                "Expected asyncio.create_subprocess_exec to be called with pgrep"
            )


@pytest.mark.asyncio
async def test_claude_reset_kills_processes_with_async_subprocess(
    mock_update, mock_context
):
    """_claude_reset must use async subprocess for kill when processes found."""
    p1, p2, p3, p4 = _patch_claude_reset_deps()
    with p1, p2, p3, p4:
        pgrep_process = AsyncMock()
        pgrep_process.communicate = AsyncMock(
            return_value=(b"1234\n5678\n", b"")
        )
        pgrep_process.returncode = 0

        kill_process = AsyncMock()
        kill_process.communicate = AsyncMock(return_value=(b"", b""))
        kill_process.returncode = 0

        async def mock_exec(*args, **kwargs):
            if args[0] == "pgrep":
                return pgrep_process
            return kill_process

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_exec,
        ) as mock_async_exec:
            from src.bot.handlers.claude_commands import _claude_reset

            await _claude_reset(mock_update, mock_context)

            # Should have called pgrep once + kill for each PID
            assert mock_async_exec.call_count >= 3, (
                f"Expected at least 3 calls (1 pgrep + 2 kill), "
                f"got {mock_async_exec.call_count}"
            )

            kill_calls = [
                c
                for c in mock_async_exec.call_args_list
                if len(c[0]) > 0 and c[0][0] == "kill"
            ]
            assert len(kill_calls) == 2
            killed_pids = {c[0][2] for c in kill_calls}
            assert killed_pids == {"1234", "5678"}
