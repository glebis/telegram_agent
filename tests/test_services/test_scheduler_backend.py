"""Tests for the scheduler abstraction."""

from datetime import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.scheduler.base import ScheduledJob, ScheduleType
from src.services.scheduler.job_queue_backend import JobQueueBackend

# ------------------------------------------------------------------
# ScheduledJob validation
# ------------------------------------------------------------------


def test_interval_job_requires_seconds():
    """INTERVAL job must have interval_seconds."""
    with pytest.raises(ValueError, match="interval_seconds"):
        ScheduledJob(
            name="test",
            callback=AsyncMock(),
            schedule_type=ScheduleType.INTERVAL,
        )


def test_daily_job_requires_times():
    """DAILY job must have daily_times."""
    with pytest.raises(ValueError, match="daily_times"):
        ScheduledJob(
            name="test",
            callback=AsyncMock(),
            schedule_type=ScheduleType.DAILY,
        )


def test_valid_interval_job():
    """Valid INTERVAL job creates without error."""
    job = ScheduledJob(
        name="test",
        callback=AsyncMock(),
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=300,
    )
    assert job.interval_seconds == 300
    assert job.enabled is True


def test_valid_daily_job():
    """Valid DAILY job creates without error."""
    job = ScheduledJob(
        name="test",
        callback=AsyncMock(),
        schedule_type=ScheduleType.DAILY,
        daily_times=[time(9, 0), time(14, 0)],
    )
    assert len(job.daily_times) == 2


# ------------------------------------------------------------------
# JobQueueBackend
# ------------------------------------------------------------------


@pytest.fixture
def mock_app():
    """Create a mock Application with a job queue."""
    app = MagicMock()
    jq = MagicMock()
    jq.run_repeating = MagicMock()
    jq.run_daily = MagicMock()
    jq.get_jobs_by_name = MagicMock(return_value=[])
    app.job_queue = jq
    return app


@pytest.fixture
def backend(mock_app):
    return JobQueueBackend(mock_app)


def test_schedule_interval(backend, mock_app):
    """Scheduling an INTERVAL job calls run_repeating."""
    cb = AsyncMock()
    job = ScheduledJob(
        name="test_interval",
        callback=cb,
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=600,
        first_delay_seconds=30,
    )
    backend.schedule(job)

    mock_app.job_queue.run_repeating.assert_called_once_with(
        cb,
        interval=600,
        first=30,
        name="test_interval",
    )
    assert "test_interval" in backend.list_jobs()


def test_schedule_daily(backend, mock_app):
    """Scheduling a DAILY job calls run_daily for each time."""
    cb = AsyncMock()
    times = [time(9, 0), time(14, 30)]
    job = ScheduledJob(
        name="test_daily",
        callback=cb,
        schedule_type=ScheduleType.DAILY,
        daily_times=times,
    )
    backend.schedule(job)

    assert mock_app.job_queue.run_daily.call_count == 2
    assert "test_daily" in backend.list_jobs()


def test_schedule_disabled_job(backend, mock_app):
    """Disabled job is not scheduled."""
    job = ScheduledJob(
        name="disabled",
        callback=AsyncMock(),
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=60,
        enabled=False,
    )
    backend.schedule(job)

    mock_app.job_queue.run_repeating.assert_not_called()
    assert "disabled" not in backend.list_jobs()


def test_cancel_job(backend, mock_app):
    """Cancel removes job from registry."""
    cb = AsyncMock()
    job = ScheduledJob(
        name="to_cancel",
        callback=cb,
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=300,
    )
    backend.schedule(job)
    assert "to_cancel" in backend.list_jobs()

    mock_ptb_job = MagicMock()
    mock_app.job_queue.get_jobs_by_name.return_value = [mock_ptb_job]

    result = backend.cancel("to_cancel")
    assert result is True
    assert "to_cancel" not in backend.list_jobs()
    mock_ptb_job.schedule_removal.assert_called_once()


def test_cancel_nonexistent(backend):
    """Cancel returns False for unknown job."""
    result = backend.cancel("nonexistent")
    assert result is False


def test_list_jobs_empty(backend):
    """Empty backend returns empty list."""
    assert backend.list_jobs() == []


def test_no_job_queue_raises(mock_app):
    """Accessing job queue when None raises RuntimeError."""
    mock_app.job_queue = None
    backend = JobQueueBackend(mock_app)

    job = ScheduledJob(
        name="test",
        callback=AsyncMock(),
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=60,
    )

    with pytest.raises(RuntimeError, match="JobQueue not available"):
        backend.schedule(job)


@pytest.mark.asyncio
async def test_stop_cancels_all(backend, mock_app):
    """stop() cancels all registered jobs."""
    for i in range(3):
        job = ScheduledJob(
            name=f"job_{i}",
            callback=AsyncMock(),
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=60,
        )
        backend.schedule(job)

    assert len(backend.list_jobs()) == 3

    await backend.stop()
    assert len(backend.list_jobs()) == 0
