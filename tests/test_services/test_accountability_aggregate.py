"""
Tests for AccountabilityService integration with TrackerAggregate.

Verifies that get_streak and count_consecutive_misses delegate to the aggregate
instead of doing raw DB/loop computation.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.tracker import CheckIn, Tracker
from src.models.tracker_aggregate import TrackerAggregate
from src.services.accountability_service import AccountabilityService


def _make_tracker(user_id: int = 100, tracker_id: int = 1, **kwargs) -> Tracker:
    t = Tracker(
        user_id=user_id,
        type=kwargs.get("type", "habit"),
        name=kwargs.get("name", "Exercise"),
        description=kwargs.get("description", None),
        check_frequency=kwargs.get("check_frequency", "daily"),
        check_time=kwargs.get("check_time", None),
        active=kwargs.get("active", True),
    )
    t.id = tracker_id
    return t


def _make_checkin(
    tracker_id: int = 1,
    user_id: int = 100,
    status: str = "completed",
    created_at: datetime | None = None,
) -> CheckIn:
    ci = CheckIn(
        tracker_id=tracker_id,
        user_id=user_id,
        status=status,
        notes=None,
    )
    ci.id = None
    ci.created_at = created_at or datetime.now(timezone.utc)
    return ci


class TestServiceUsesAggregate:
    """Verify AccountabilityService.load_aggregate exists and is used."""

    @pytest.mark.asyncio
    async def test_load_aggregate_returns_aggregate(self):
        """load_aggregate should return a TrackerAggregate."""
        tracker = _make_tracker(user_id=100, tracker_id=5)
        today = date.today()
        ci = _make_checkin(
            tracker_id=5,
            user_id=100,
            status="completed",
            created_at=datetime(
                today.year, today.month, today.day, 12, 0, tzinfo=timezone.utc
            ),
        )

        # Mock DB session to return our tracker and check-ins
        mock_session = AsyncMock()

        # First execute call: select Tracker
        tracker_result = MagicMock()
        tracker_result.scalar_one_or_none.return_value = tracker

        # Second execute call: select CheckIn
        checkin_result = MagicMock()
        checkin_scalars = MagicMock()
        checkin_scalars.all.return_value = [ci]
        checkin_result.scalars.return_value = checkin_scalars

        mock_session.execute = AsyncMock(side_effect=[tracker_result, checkin_result])

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.services.accountability_service.get_db_session",
            return_value=mock_ctx,
        ):
            agg = await AccountabilityService.load_aggregate(100, 5)

        assert isinstance(agg, TrackerAggregate)
        assert agg.tracker_id == 5
        assert agg.compute_streak() == 1

    @pytest.mark.asyncio
    async def test_load_aggregate_returns_none_for_missing_tracker(self):
        """load_aggregate returns None if tracker not found."""
        mock_session = AsyncMock()
        tracker_result = MagicMock()
        tracker_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=tracker_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.services.accountability_service.get_db_session",
            return_value=mock_ctx,
        ):
            agg = await AccountabilityService.load_aggregate(100, 999)

        assert agg is None

    @pytest.mark.asyncio
    async def test_get_streak_delegates_to_aggregate(self):
        """get_streak should call load_aggregate and delegate to compute_streak."""
        tracker = _make_tracker(user_id=100, tracker_id=5)
        today = date.today()
        ci = _make_checkin(
            tracker_id=5,
            user_id=100,
            status="completed",
            created_at=datetime(
                today.year, today.month, today.day, 12, 0, tzinfo=timezone.utc
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        with patch.object(
            AccountabilityService,
            "load_aggregate",
            new_callable=AsyncMock,
            return_value=agg,
        ) as mock_load:
            streak = await AccountabilityService.get_streak(100, 5)

        mock_load.assert_called_once_with(100, 5)
        assert streak == 1

    @pytest.mark.asyncio
    async def test_count_consecutive_misses_delegates_to_aggregate(self):
        """count_consecutive_misses should use load_aggregate."""
        tracker = _make_tracker(user_id=100, tracker_id=5)
        yesterday = date.today() - timedelta(days=1)
        ci = _make_checkin(
            tracker_id=5,
            user_id=100,
            status="completed",
            created_at=datetime(
                yesterday.year,
                yesterday.month,
                yesterday.day,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        with patch.object(
            AccountabilityService,
            "load_aggregate",
            new_callable=AsyncMock,
            return_value=agg,
        ) as mock_load:
            misses = await AccountabilityService.count_consecutive_misses(100, 5)

        mock_load.assert_called_once_with(100, 5)
        assert misses == 1
