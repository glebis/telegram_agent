"""Tests for /heartbeat command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.heartbeat_commands import heartbeat_command


def _make_update(user_id=123, chat_id=456):
    """Create a mock Update with user and chat."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_heartbeat_requires_admin():
    """Non-admin user is rejected."""
    update = _make_update()
    context = MagicMock()

    with patch(
        "src.services.claude_code_service.is_claude_code_admin",
        new_callable=AsyncMock,
        return_value=False,
    ):
        await heartbeat_command(update, context)

    update.message.reply_text.assert_called_once_with(
        "This command is restricted to admins."
    )


@pytest.mark.asyncio
async def test_heartbeat_admin_triggers_run():
    """Admin user gets heartbeat running."""
    update = _make_update()
    context = MagicMock()

    admin_mock = AsyncMock(return_value=True)
    task_mock = MagicMock()

    with patch(
        "src.services.claude_code_service.is_claude_code_admin",
        admin_mock,
    ):
        with patch(
            "src.utils.task_tracker.create_tracked_task",
            task_mock,
        ):
            await heartbeat_command(update, context)
            # Assertions inside patch context
            admin_mock.assert_called_once()
            update.message.reply_text.assert_called_with("Running health checks...")
            task_mock.assert_called_once()


@pytest.mark.asyncio
async def test_heartbeat_no_user():
    """Gracefully handles missing user."""
    update = MagicMock()
    update.effective_user = None
    update.effective_chat = MagicMock()
    context = MagicMock()

    await heartbeat_command(update, context)


@pytest.mark.asyncio
async def test_heartbeat_no_chat():
    """Gracefully handles missing chat."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_chat = None
    context = MagicMock()

    await heartbeat_command(update, context)
