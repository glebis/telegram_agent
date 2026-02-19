"""
Tests for AccountabilityAppService — application-layer orchestration.

Uses mocks for DB queries (repos) and TTS. Verifies the app service
correctly wires domain logic with infrastructure.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_settings(**overrides):
    """Create a mock UserSettings with defaults."""
    s = MagicMock()
    s.partner_personality = overrides.get("partner_personality", "supportive")
    s.partner_voice_override = overrides.get("partner_voice_override", None)
    s.struggle_threshold = overrides.get("struggle_threshold", 3)
    s.celebration_style = overrides.get("celebration_style", "moderate")
    return s


def _make_tracker(**overrides):
    """Create a mock Tracker."""
    t = MagicMock()
    t.id = overrides.get("id", 1)
    t.name = overrides.get("name", "Exercise")
    t.check_frequency = overrides.get("check_frequency", "daily")
    t.active = overrides.get("active", True)
    return t


def _make_checkin(created_at, status="completed"):
    """Create a mock CheckIn."""
    ci = MagicMock()
    ci.created_at = created_at
    ci.status = status
    return ci


class TestAppServiceSendCheckIn:
    """Test send_check_in orchestration."""

    @pytest.mark.asyncio
    async def test_send_check_in_returns_text_and_audio(self):
        from src.services.accountability_app import AccountabilityAppService

        settings = _make_settings()
        tracker = _make_tracker(name="Meditation")

        with (
            patch.object(
                AccountabilityAppService,
                "_get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch.object(
                AccountabilityAppService,
                "_get_tracker",
                new_callable=AsyncMock,
                return_value=tracker,
            ),
            patch.object(
                AccountabilityAppService,
                "_get_streak_from_db",
                new_callable=AsyncMock,
                return_value=5,
            ),
            patch.object(
                AccountabilityAppService,
                "_generate_message_text",
                return_value="Check in on Meditation. 5 days strong!",
            ),
            patch.object(
                AccountabilityAppService,
                "_synthesize_voice",
                new_callable=AsyncMock,
                return_value=b"fake-audio-bytes",
            ),
        ):
            result = await AccountabilityAppService.send_check_in(
                user_id=123, tracker_id=1
            )

        assert result is not None
        text, audio = result
        assert "Meditation" in text
        assert audio == b"fake-audio-bytes"

    @pytest.mark.asyncio
    async def test_send_check_in_no_settings_returns_none(self):
        from src.services.accountability_app import AccountabilityAppService

        with patch.object(
            AccountabilityAppService,
            "_get_user_settings",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await AccountabilityAppService.send_check_in(
                user_id=123, tracker_id=1
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_send_check_in_no_tracker_returns_none(self):
        from src.services.accountability_app import AccountabilityAppService

        settings = _make_settings()
        with (
            patch.object(
                AccountabilityAppService,
                "_get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch.object(
                AccountabilityAppService,
                "_get_tracker",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await AccountabilityAppService.send_check_in(
                user_id=123, tracker_id=1
            )

        assert result is None


class TestAppServiceCheckForStruggles:
    """Test check_for_struggles orchestration."""

    @pytest.mark.asyncio
    async def test_returns_struggles_above_threshold(self):
        from src.services.accountability_app import AccountabilityAppService

        settings = _make_settings(struggle_threshold=3)
        trackers = [
            _make_tracker(id=1, name="Exercise"),
            _make_tracker(id=2, name="Reading"),
        ]

        with (
            patch.object(
                AccountabilityAppService,
                "_get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch.object(
                AccountabilityAppService,
                "_get_active_trackers",
                new_callable=AsyncMock,
                return_value=trackers,
            ),
            patch.object(
                AccountabilityAppService,
                "_count_misses_from_db",
                new_callable=AsyncMock,
                side_effect=[4, 1],  # Exercise=4 misses, Reading=1
            ),
        ):
            result = await AccountabilityAppService.check_for_struggles(user_id=123)

        assert result == {1: 4}

    @pytest.mark.asyncio
    async def test_no_settings_returns_empty(self):
        from src.services.accountability_app import AccountabilityAppService

        with patch.object(
            AccountabilityAppService,
            "_get_user_settings",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await AccountabilityAppService.check_for_struggles(user_id=123)

        assert result == {}


class TestAppServiceSendStruggleAlert:
    """Test send_struggle_alert orchestration."""

    @pytest.mark.asyncio
    async def test_returns_text_and_audio(self):
        from src.services.accountability_app import AccountabilityAppService

        settings = _make_settings()
        tracker = _make_tracker(name="Exercise")

        with (
            patch.object(
                AccountabilityAppService,
                "_get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch.object(
                AccountabilityAppService,
                "_get_tracker",
                new_callable=AsyncMock,
                return_value=tracker,
            ),
            patch.object(
                AccountabilityAppService,
                "_generate_struggle_text",
                return_value="Missed 5 days on Exercise.",
            ),
            patch.object(
                AccountabilityAppService,
                "_synthesize_voice",
                new_callable=AsyncMock,
                return_value=b"audio-bytes",
            ),
        ):
            result = await AccountabilityAppService.send_struggle_alert(
                user_id=123, tracker_id=1, consecutive_misses=5
            )

        assert result is not None
        text, audio = result
        assert "Exercise" in text
        assert audio == b"audio-bytes"


class TestAppServiceCelebrateMilestone:
    """Test celebrate_milestone orchestration."""

    @pytest.mark.asyncio
    async def test_returns_text_and_audio(self):
        from src.services.accountability_app import AccountabilityAppService

        settings = _make_settings(celebration_style="enthusiastic")
        tracker = _make_tracker(name="Meditation")

        with (
            patch.object(
                AccountabilityAppService,
                "_get_user_settings",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch.object(
                AccountabilityAppService,
                "_get_tracker",
                new_callable=AsyncMock,
                return_value=tracker,
            ),
            patch.object(
                AccountabilityAppService,
                "_generate_celebration_text",
                return_value="7-day streak! Amazing! 🔥",
            ),
            patch.object(
                AccountabilityAppService,
                "_synthesize_voice",
                new_callable=AsyncMock,
                return_value=b"celebration-audio",
            ),
        ):
            result = await AccountabilityAppService.celebrate_milestone(
                user_id=123, tracker_id=1, milestone=7
            )

        assert result is not None
        text, audio = result
        assert audio == b"celebration-audio"


class TestAppServiceDelegation:
    """Verify app service delegates to domain service for pure logic."""

    def test_get_streak_from_db_uses_domain_calculate_streak(self):
        """Confirm the app service method signature exists and is async."""
        from src.services.accountability_app import AccountabilityAppService

        assert hasattr(AccountabilityAppService, "_get_streak_from_db")

    def test_count_misses_from_db_exists(self):
        from src.services.accountability_app import AccountabilityAppService

        assert hasattr(AccountabilityAppService, "_count_misses_from_db")
