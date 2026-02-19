"""
Tests verifying accountability_scheduler uses AccountabilityAppService
instead of the old AccountabilityService.

Slice 3: After updating the scheduler imports, these confirm the
new wiring is correct.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSchedulerImportsAppService:
    """Verify scheduler references AccountabilityAppService."""

    def test_send_checkin_reminder_imports_app_service(self):
        """The send_checkin_reminder function should import from accountability_app."""
        import inspect

        from src.services.accountability_scheduler import send_checkin_reminder

        source = inspect.getsource(send_checkin_reminder)
        assert "AccountabilityAppService" in source
        assert "accountability_app" in source

    def test_check_struggles_imports_app_service(self):
        """The check_struggles function should import from accountability_app."""
        import inspect

        from src.services.accountability_scheduler import check_struggles

        source = inspect.getsource(check_struggles)
        assert "AccountabilityAppService" in source
        assert "accountability_app" in source

    def test_check_struggles_fallback_imports_app_service(self):
        """The fallback message gen in check_struggles should use app service."""
        import inspect

        from src.services.accountability_scheduler import check_struggles

        source = inspect.getsource(check_struggles)
        # Should NOT import the old AccountabilityService
        assert "from .accountability_service import AccountabilityService" not in source


class TestSchedulerCallsAppService:
    """Verify the scheduler delegates to AccountabilityAppService methods."""

    @pytest.mark.asyncio
    async def test_send_checkin_calls_app_send_check_in(self):
        """send_checkin_reminder should call AccountabilityAppService.send_check_in."""
        from src.services.accountability_scheduler import send_checkin_reminder

        context = MagicMock()
        context.job = MagicMock()
        context.job.data = {"user_id": 123, "chat_id": 456, "locale": "en"}
        context.bot.send_message = AsyncMock()
        context.bot.send_voice = AsyncMock()

        mock_tracker = MagicMock()
        mock_tracker.id = 1
        mock_tracker.name = "Exercise"
        mock_tracker.type = "habit"

        with (
            patch(
                "src.services.accountability_scheduler._is_quiet_hours",
                return_value=False,
            ),
            patch(
                "src.services.accountability_scheduler.get_db_session"
            ) as mock_db,
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
            patch(
                "src.services.accountability_scheduler._is_accountability_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.services.accountability_app.AccountabilityAppService.send_check_in",
                new_callable=AsyncMock,
                return_value=("Check in!", b"audio"),
            ) as mock_send,
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_tracker]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_db.return_value = mock_session

            await send_checkin_reminder(context)

            mock_send.assert_called_once_with(123, 1)

    @pytest.mark.asyncio
    async def test_check_struggles_calls_app_service(self):
        """check_struggles should call AccountabilityAppService methods."""
        from src.services.accountability_scheduler import check_struggles

        context = MagicMock()
        context.job = MagicMock()
        context.job.data = {"user_id": 123, "chat_id": 456}
        context.bot.send_message = AsyncMock()
        context.bot.send_voice = AsyncMock()

        with (
            patch(
                "src.services.accountability_scheduler._is_accountability_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.services.accountability_app.AccountabilityAppService.check_for_struggles",
                new_callable=AsyncMock,
                return_value={1: 5},
            ) as mock_struggles,
            patch(
                "src.services.accountability_app.AccountabilityAppService.send_struggle_alert",
                new_callable=AsyncMock,
                return_value=("You missed 5 days", b"audio"),
            ) as mock_alert,
        ):
            await check_struggles(context)

            mock_struggles.assert_called_once_with(123)
            mock_alert.assert_called_once_with(123, 1, 5)
