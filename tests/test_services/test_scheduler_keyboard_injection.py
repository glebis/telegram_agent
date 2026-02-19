"""Tests that send_checkin_reminder uses injected KeyboardBuilder."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.ports.keyboard_builder import KeyboardBuilder


class TestCheckinReminderKeyboardInjection:
    """send_checkin_reminder must accept and use a KeyboardBuilder parameter."""

    @pytest.fixture
    def mock_keyboard_builder(self):
        builder = MagicMock(spec=KeyboardBuilder)
        builder.build_inline_keyboard.return_value = "FAKE_MARKUP"
        return builder

    @pytest.mark.asyncio
    async def test_send_checkin_reminder_accepts_keyboard_builder(
        self, mock_keyboard_builder
    ):
        """send_checkin_reminder must accept a keyboard_builder keyword argument."""
        from src.services.accountability_scheduler import send_checkin_reminder

        context = MagicMock()
        context.job.data = {"user_id": 1, "chat_id": 123, "locale": "en"}
        context.bot.send_message = AsyncMock()

        with (
            patch("src.services.accountability_scheduler.get_db_session") as mock_db,
            patch(
                "src.services.accountability_scheduler._is_quiet_hours",
                return_value=False,
            ),
            patch(
                "src.services.accountability_scheduler._is_accountability_enabled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

            await send_checkin_reminder(context, keyboard_builder=mock_keyboard_builder)

    @pytest.mark.asyncio
    async def test_send_checkin_reminder_uses_builder_for_markup(
        self, mock_keyboard_builder
    ):
        """When there are unchecked trackers, build_inline_keyboard is called."""
        from src.services.accountability_scheduler import send_checkin_reminder

        context = MagicMock()
        context.job.data = {"user_id": 1, "chat_id": 123, "locale": "en"}
        context.bot.send_message = AsyncMock()

        mock_tracker = MagicMock()
        mock_tracker.id = 42
        mock_tracker.name = "Exercise"
        mock_tracker.type = "habit"

        with (
            patch("src.services.accountability_scheduler.get_db_session") as mock_db,
            patch(
                "src.services.accountability_scheduler._is_quiet_hours",
                return_value=False,
            ),
            patch(
                "src.services.accountability_scheduler._is_accountability_enabled",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.services.tracker_queries.get_today_checkin",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.services.tracker_queries.get_streak",
                new_callable=AsyncMock,
                return_value=3,
            ),
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_tracker]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

            await send_checkin_reminder(context, keyboard_builder=mock_keyboard_builder)

        mock_keyboard_builder.build_inline_keyboard.assert_called_once()
        call_kwargs = context.bot.send_message.call_args.kwargs
        assert call_kwargs["reply_markup"] == "FAKE_MARKUP"
