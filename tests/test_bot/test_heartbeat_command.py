"""Tests for /heartbeat command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.heartbeat_commands import heartbeat_command
from src.core.authorization import AuthTier


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
    """Non-owner user is rejected by require_tier(OWNER)."""
    update = _make_update()
    context = MagicMock()

    with patch(
        "src.core.authorization.get_user_tier",
        return_value=AuthTier.USER,
    ):
        await heartbeat_command(update, context)

    update.message.reply_text.assert_called_once_with(
        "You are not authorized to use this command."
    )


@pytest.mark.asyncio
async def test_heartbeat_admin_triggers_run():
    """Owner user gets heartbeat running."""
    update = _make_update()
    context = MagicMock()

    task_mock = MagicMock()

    with patch(
        "src.core.authorization.get_user_tier",
        return_value=AuthTier.OWNER,
    ):
        with patch(
            "src.bot.handlers.heartbeat_commands.task_tracker.create_tracked_task",
            task_mock,
        ):
            with patch(
                "src.services.heartbeat_service.get_heartbeat_service",
            ):
                await heartbeat_command(update, context)
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
