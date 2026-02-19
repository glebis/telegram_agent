"""
Tests that accountability_service raises typed domain errors
instead of silently returning None.

Each test mocks the DB/TTS layer and asserts the specific exception.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.errors import TrackerNotFound, UserSettingsNotFound, VoiceSynthesisFailure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db_session(execute_return=None):
    """Return a mock async context-manager session."""
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = execute_return
    session.execute = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


# ---------------------------------------------------------------------------
# send_check_in
# ---------------------------------------------------------------------------


class TestSendCheckInErrors:
    """send_check_in must raise typed errors, not return None."""

    @pytest.mark.asyncio
    async def test_raises_user_settings_not_found(self):
        """When there are no user settings, raise UserSettingsNotFound."""
        with patch(
            "src.services.accountability_service.AccountabilityService.get_user_settings",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from src.services.accountability_service import AccountabilityService

            with pytest.raises(UserSettingsNotFound) as exc_info:
                await AccountabilityService.send_check_in(user_id=42, tracker_id=1)
            assert exc_info.value.user_id == 42

    @pytest.mark.asyncio
    async def test_raises_tracker_not_found(self):
        """When the tracker doesn't exist, raise TrackerNotFound."""
        settings = MagicMock()
        settings.partner_personality = "supportive"
        settings.partner_voice_override = None

        with (
            patch(
                "src.services.accountability_service.AccountabilityService.get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch(
                "src.services.accountability_service.get_db_session"
            ) as mock_db,
        ):
            mock_db.return_value = _mock_db_session(execute_return=None)

            from src.services.accountability_service import AccountabilityService

            with pytest.raises(TrackerNotFound) as exc_info:
                await AccountabilityService.send_check_in(user_id=42, tracker_id=999)
            assert exc_info.value.tracker_id == 999

    @pytest.mark.asyncio
    async def test_raises_voice_synthesis_failure(self):
        """When TTS fails, raise VoiceSynthesisFailure instead of returning None."""
        settings = MagicMock()
        settings.partner_personality = "supportive"
        settings.partner_voice_override = None

        tracker = MagicMock()
        tracker.name = "Exercise"

        with (
            patch(
                "src.services.accountability_service.AccountabilityService.get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch(
                "src.services.accountability_service.get_db_session"
            ) as mock_db,
            patch(
                "src.services.accountability_service.AccountabilityService.get_streak",
                new_callable=AsyncMock,
                return_value=3,
            ),
            patch(
                "src.services.accountability_service.synthesize_voice_mp3",
                new_callable=AsyncMock,
                side_effect=RuntimeError("TTS provider timeout"),
            ),
        ):
            mock_db.return_value = _mock_db_session(execute_return=tracker)

            from src.services.accountability_service import AccountabilityService

            with pytest.raises(VoiceSynthesisFailure):
                await AccountabilityService.send_check_in(user_id=42, tracker_id=1)


# ---------------------------------------------------------------------------
# send_struggle_alert
# ---------------------------------------------------------------------------


class TestSendStruggleAlertErrors:
    """send_struggle_alert must raise typed errors, not return None."""

    @pytest.mark.asyncio
    async def test_raises_user_settings_not_found(self):
        with patch(
            "src.services.accountability_service.AccountabilityService.get_user_settings",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from src.services.accountability_service import AccountabilityService

            with pytest.raises(UserSettingsNotFound):
                await AccountabilityService.send_struggle_alert(
                    user_id=42, tracker_id=1, consecutive_misses=5
                )

    @pytest.mark.asyncio
    async def test_raises_tracker_not_found(self):
        settings = MagicMock()
        settings.partner_personality = "supportive"
        settings.partner_voice_override = None

        with (
            patch(
                "src.services.accountability_service.AccountabilityService.get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch(
                "src.services.accountability_service.get_db_session"
            ) as mock_db,
        ):
            mock_db.return_value = _mock_db_session(execute_return=None)

            from src.services.accountability_service import AccountabilityService

            with pytest.raises(TrackerNotFound) as exc_info:
                await AccountabilityService.send_struggle_alert(
                    user_id=42, tracker_id=999, consecutive_misses=5
                )
            assert exc_info.value.tracker_id == 999

    @pytest.mark.asyncio
    async def test_raises_voice_synthesis_failure(self):
        settings = MagicMock()
        settings.partner_personality = "supportive"
        settings.partner_voice_override = None

        tracker = MagicMock()
        tracker.name = "Exercise"

        with (
            patch(
                "src.services.accountability_service.AccountabilityService.get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch(
                "src.services.accountability_service.get_db_session"
            ) as mock_db,
            patch(
                "src.services.accountability_service.synthesize_voice_mp3",
                new_callable=AsyncMock,
                side_effect=RuntimeError("TTS boom"),
            ),
        ):
            mock_db.return_value = _mock_db_session(execute_return=tracker)

            from src.services.accountability_service import AccountabilityService

            with pytest.raises(VoiceSynthesisFailure):
                await AccountabilityService.send_struggle_alert(
                    user_id=42, tracker_id=1, consecutive_misses=5
                )


# ---------------------------------------------------------------------------
# celebrate_milestone
# ---------------------------------------------------------------------------


class TestCelebrateMilestoneErrors:
    """celebrate_milestone must raise typed errors, not return None."""

    @pytest.mark.asyncio
    async def test_raises_user_settings_not_found(self):
        with patch(
            "src.services.accountability_service.AccountabilityService.get_user_settings",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from src.services.accountability_service import AccountabilityService

            with pytest.raises(UserSettingsNotFound):
                await AccountabilityService.celebrate_milestone(
                    user_id=42, tracker_id=1, milestone=7
                )

    @pytest.mark.asyncio
    async def test_raises_tracker_not_found(self):
        settings = MagicMock()
        settings.partner_personality = "supportive"
        settings.celebration_style = "moderate"
        settings.partner_voice_override = None

        with (
            patch(
                "src.services.accountability_service.AccountabilityService.get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch(
                "src.services.accountability_service.get_db_session"
            ) as mock_db,
        ):
            mock_db.return_value = _mock_db_session(execute_return=None)

            from src.services.accountability_service import AccountabilityService

            with pytest.raises(TrackerNotFound) as exc_info:
                await AccountabilityService.celebrate_milestone(
                    user_id=42, tracker_id=999, milestone=7
                )
            assert exc_info.value.tracker_id == 999

    @pytest.mark.asyncio
    async def test_raises_voice_synthesis_failure(self):
        settings = MagicMock()
        settings.partner_personality = "supportive"
        settings.celebration_style = "moderate"
        settings.partner_voice_override = None

        tracker = MagicMock()
        tracker.name = "Exercise"

        with (
            patch(
                "src.services.accountability_service.AccountabilityService.get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch(
                "src.services.accountability_service.get_db_session"
            ) as mock_db,
            patch(
                "src.services.accountability_service.synthesize_voice_mp3",
                new_callable=AsyncMock,
                side_effect=RuntimeError("TTS error"),
            ),
        ):
            mock_db.return_value = _mock_db_session(execute_return=tracker)

            from src.services.accountability_service import AccountabilityService

            with pytest.raises(VoiceSynthesisFailure):
                await AccountabilityService.celebrate_milestone(
                    user_id=42, tracker_id=1, milestone=7
                )
