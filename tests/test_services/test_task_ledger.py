"""Tests for the task ledger service (persistent scheduled task management)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.models.base import Base
from src.models.scheduled_task import ContextMode, TaskRunStatus
from src.services.task_ledger_service import TaskLedgerService


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite database and return an async session."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def service(db_session):
    """Create a TaskLedgerService that uses the test session."""
    return TaskLedgerService(session=db_session)


# ------------------------------------------------------------------
# CRUD: create
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_with_cron(service):
    """Create a task with cron schedule."""
    task = await service.create_task(
        chat_id=123,
        task_type="daily_health_review",
        schedule_cron="30 9 * * *",
        context_mode="shared",
    )
    assert task.id is not None
    assert task.chat_id == 123
    assert task.task_type == "daily_health_review"
    assert task.schedule_cron == "30 9 * * *"
    assert task.context_mode == ContextMode.SHARED
    assert task.enabled is True


@pytest.mark.asyncio
async def test_create_task_with_interval(service):
    """Create a task with interval schedule."""
    task = await service.create_task(
        chat_id=456,
        task_type="poll_check",
        schedule_interval_seconds=3600,
    )
    assert task.schedule_interval_seconds == 3600
    assert task.schedule_cron is None
    assert task.context_mode == ContextMode.ISOLATED  # default


@pytest.mark.asyncio
async def test_create_task_with_once_at(service):
    """Create a one-shot task scheduled for a specific time."""
    target = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    task = await service.create_task(
        chat_id=789,
        task_type="reminder",
        schedule_once_at=target,
    )
    assert task.schedule_once_at == target
    assert task.next_run_at == target


@pytest.mark.asyncio
async def test_create_task_defaults_isolated(service):
    """Context mode defaults to 'isolated' when not specified."""
    task = await service.create_task(
        chat_id=100,
        task_type="test_task",
        schedule_cron="0 * * * *",
    )
    assert task.context_mode == ContextMode.ISOLATED


# ------------------------------------------------------------------
# CRUD: list
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tasks_by_chat_id(service):
    """List tasks filters by chat_id."""
    await service.create_task(chat_id=1, task_type="a", schedule_cron="* * * * *")
    await service.create_task(chat_id=1, task_type="b", schedule_cron="* * * * *")
    await service.create_task(chat_id=2, task_type="c", schedule_cron="* * * * *")

    tasks_1 = await service.list_tasks(chat_id=1)
    tasks_2 = await service.list_tasks(chat_id=2)

    assert len(tasks_1) == 2
    assert len(tasks_2) == 1


@pytest.mark.asyncio
async def test_list_tasks_all(service):
    """List all tasks when no chat_id filter."""
    await service.create_task(chat_id=1, task_type="a", schedule_cron="* * * * *")
    await service.create_task(chat_id=2, task_type="b", schedule_cron="* * * * *")

    all_tasks = await service.list_tasks()
    assert len(all_tasks) == 2


# ------------------------------------------------------------------
# CRUD: get
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_task_exists(service):
    """Get a task by ID returns the correct task."""
    created = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    fetched = await service.get_task(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.task_type == "test"


@pytest.mark.asyncio
async def test_get_task_nonexistent(service):
    """Get a nonexistent task returns None."""
    result = await service.get_task(99999)
    assert result is None


# ------------------------------------------------------------------
# CRUD: toggle
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_task_disables(service):
    """Toggle an enabled task disables it."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    assert task.enabled is True

    toggled = await service.toggle_task(task.id)
    assert toggled.enabled is False


@pytest.mark.asyncio
async def test_toggle_task_enables(service):
    """Toggle a disabled task enables it."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    await service.toggle_task(task.id)  # disable
    toggled = await service.toggle_task(task.id)  # enable
    assert toggled.enabled is True


@pytest.mark.asyncio
async def test_toggle_nonexistent_task(service):
    """Toggle a nonexistent task raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await service.toggle_task(99999)


# ------------------------------------------------------------------
# CRUD: delete
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_task(service):
    """Delete removes task and returns True."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    result = await service.delete_task(task.id)
    assert result is True

    fetched = await service.get_task(task.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_nonexistent_task(service):
    """Delete a nonexistent task returns False."""
    result = await service.delete_task(99999)
    assert result is False


# ------------------------------------------------------------------
# Run logging
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_run_success(service):
    """Log a successful task run."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    log = await service.log_run(
        task_id=task.id,
        status="success",
        result_summary="Completed in 2.3s",
    )
    assert log.id is not None
    assert log.task_id == task.id
    assert log.status == TaskRunStatus.SUCCESS
    assert log.result_summary == "Completed in 2.3s"
    assert log.error_message is None
    assert log.started_at is not None
    assert log.completed_at is not None


@pytest.mark.asyncio
async def test_log_run_error(service):
    """Log a failed task run with error message."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    log = await service.log_run(
        task_id=task.id,
        status="error",
        error_message="Connection timeout",
    )
    assert log.status == TaskRunStatus.ERROR
    assert log.error_message == "Connection timeout"


@pytest.mark.asyncio
async def test_log_run_timeout(service):
    """Log a timed-out task run."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    log = await service.log_run(task_id=task.id, status="timeout")
    assert log.status == TaskRunStatus.TIMEOUT


# ------------------------------------------------------------------
# Run history
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_history(service):
    """Get run history returns logs in reverse chronological order."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    await service.log_run(task_id=task.id, status="success", result_summary="run 1")
    await service.log_run(task_id=task.id, status="error", error_message="fail")
    await service.log_run(task_id=task.id, status="success", result_summary="run 3")

    history = await service.get_run_history(task.id, limit=10)
    assert len(history) == 3
    # Most recent first
    assert history[0].result_summary == "run 3"


@pytest.mark.asyncio
async def test_get_run_history_limit(service):
    """Get run history respects the limit parameter."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    for i in range(5):
        await service.log_run(
            task_id=task.id, status="success", result_summary=f"run {i}"
        )

    history = await service.get_run_history(task.id, limit=3)
    assert len(history) == 3


@pytest.mark.asyncio
async def test_get_run_history_empty(service):
    """Get run history returns empty list for task with no runs."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *"
    )
    history = await service.get_run_history(task.id)
    assert history == []


# ------------------------------------------------------------------
# Context mode field values
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_mode_shared(service):
    """Context mode can be set to 'shared'."""
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_cron="0 0 * * *", context_mode="shared"
    )
    assert task.context_mode == ContextMode.SHARED
    assert task.context_mode.value == "shared"


@pytest.mark.asyncio
async def test_context_mode_isolated(service):
    """Context mode can be set to 'isolated'."""
    task = await service.create_task(
        chat_id=10,
        task_type="test",
        schedule_cron="0 0 * * *",
        context_mode="isolated",
    )
    assert task.context_mode == ContextMode.ISOLATED
    assert task.context_mode.value == "isolated"


# ------------------------------------------------------------------
# get_tasks_due
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tasks_due_returns_due_enabled(service):
    """get_tasks_due returns enabled tasks past their next_run_at."""
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_once_at=past
    )
    # next_run_at is set to schedule_once_at by create_task
    due = await service.get_tasks_due()
    assert len(due) == 1
    assert due[0].id == task.id


@pytest.mark.asyncio
async def test_get_tasks_due_excludes_disabled(service):
    """get_tasks_due excludes disabled tasks."""
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    task = await service.create_task(
        chat_id=10, task_type="test", schedule_once_at=past
    )
    await service.toggle_task(task.id)  # disable

    due = await service.get_tasks_due()
    assert len(due) == 0


@pytest.mark.asyncio
async def test_get_tasks_due_excludes_future(service):
    """get_tasks_due excludes tasks with next_run_at in the future."""
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    await service.create_task(chat_id=10, task_type="test", schedule_once_at=future)
    due = await service.get_tasks_due()
    assert len(due) == 0


@pytest.mark.asyncio
async def test_get_tasks_due_excludes_null_next_run(service):
    """get_tasks_due excludes tasks where next_run_at is None."""
    await service.create_task(chat_id=10, task_type="test", schedule_cron="0 0 * * *")
    # Cron tasks start with next_run_at=None until the scheduler computes it
    due = await service.get_tasks_due()
    assert len(due) == 0


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_run_nonexistent_task(service):
    """Logging a run for a nonexistent task_id raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await service.log_run(task_id=99999, status="success")


@pytest.mark.asyncio
async def test_get_run_history_nonexistent_task(service):
    """Get run history for a nonexistent task returns empty list."""
    history = await service.get_run_history(99999)
    assert history == []
