"""
Task ledger service — persistent CRUD for scheduled tasks and run history.

Provides create/list/get/toggle/delete for ScheduledTask rows and
log_run/get_run_history for TaskRunLog entries.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models.scheduled_task import (
    ContextMode,
    ScheduledTask,
    TaskRunLog,
    TaskRunStatus,
)

logger = logging.getLogger(__name__)


class TaskLedgerService:
    """Service layer for the persistent task ledger.

    When *session* is provided (e.g. in tests), all operations use that
    session directly.  Otherwise each public method opens its own session
    via ``get_db_session()``.
    """

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session

    # -- helpers --------------------------------------------------------

    async def _get_session(self):
        """Return the injected session or open a new one."""
        if self._session is not None:
            return self._session
        return None  # caller must use get_db_session()

    # -- CRUD -----------------------------------------------------------

    async def create_task(
        self,
        chat_id: int,
        task_type: str,
        schedule_cron: Optional[str] = None,
        schedule_interval_seconds: Optional[int] = None,
        schedule_once_at: Optional[datetime] = None,
        context_mode: str = "isolated",
    ) -> ScheduledTask:
        """Create a new scheduled task.

        Args:
            chat_id: Telegram chat ID.
            task_type: Identifier for the kind of task (e.g. ``"daily_health_review"``).
            schedule_cron: Cron expression (mutually exclusive with others).
            schedule_interval_seconds: Repeat every N seconds.
            schedule_once_at: One-shot datetime.
            context_mode: ``"shared"`` or ``"isolated"`` (default).

        Returns:
            The newly created ``ScheduledTask``.
        """
        mode = ContextMode(context_mode)

        # For one-shot tasks, pre-populate next_run_at
        next_run = schedule_once_at

        task = ScheduledTask(
            chat_id=chat_id,
            task_type=task_type,
            schedule_cron=schedule_cron,
            schedule_interval_seconds=schedule_interval_seconds,
            schedule_once_at=schedule_once_at,
            context_mode=mode,
            enabled=True,
            next_run_at=next_run,
        )

        session = self._session
        if session is not None:
            session.add(task)
            await session.flush()
            return task

        async with get_db_session() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task

    async def list_tasks(self, chat_id: Optional[int] = None) -> List[ScheduledTask]:
        """List tasks, optionally filtered by chat_id."""
        stmt = select(ScheduledTask).order_by(ScheduledTask.id)
        if chat_id is not None:
            stmt = stmt.where(ScheduledTask.chat_id == chat_id)

        session = self._session
        if session is not None:
            result = await session.execute(stmt)
            return list(result.scalars().all())

        async with get_db_session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_task(self, task_id: int) -> Optional[ScheduledTask]:
        """Get a single task by primary key."""
        stmt = select(ScheduledTask).where(ScheduledTask.id == task_id)

        session = self._session
        if session is not None:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

        async with get_db_session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def toggle_task(self, task_id: int) -> ScheduledTask:
        """Toggle the *enabled* flag on a task.

        Raises:
            ValueError: If the task does not exist.
        """
        session = self._session
        if session is not None:
            task = await self.get_task(task_id)
            if task is None:
                raise ValueError(f"Task {task_id} not found")
            task.enabled = not task.enabled
            await session.flush()
            return task

        async with get_db_session() as session:
            result = await session.execute(
                select(ScheduledTask).where(ScheduledTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"Task {task_id} not found")
            task.enabled = not task.enabled
            await session.commit()
            await session.refresh(task)
            return task

    async def delete_task(self, task_id: int) -> bool:
        """Delete a task by ID.  Returns ``True`` if deleted, ``False`` if not found."""
        session = self._session
        if session is not None:
            task = await self.get_task(task_id)
            if task is None:
                return False
            await session.delete(task)
            await session.flush()
            return True

        async with get_db_session() as session:
            result = await session.execute(
                select(ScheduledTask).where(ScheduledTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return False
            await session.delete(task)
            await session.commit()
            return True

    # -- Run logging ----------------------------------------------------

    async def log_run(
        self,
        task_id: int,
        status: str,
        result_summary: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> TaskRunLog:
        """Record an execution attempt for a task.

        Args:
            task_id: The task that was executed.
            status: ``"success"``, ``"error"``, or ``"timeout"``.
            result_summary: Optional human-readable result.
            error_message: Optional error details.

        Raises:
            ValueError: If the task does not exist.
        """
        run_status = TaskRunStatus(status)
        now = datetime.now(timezone.utc)

        session = self._session
        if session is not None:
            task = await self.get_task(task_id)
            if task is None:
                raise ValueError(f"Task {task_id} not found")
            log = TaskRunLog(
                task_id=task_id,
                status=run_status,
                started_at=now,
                completed_at=now,
                result_summary=result_summary,
                error_message=error_message,
            )
            session.add(log)
            await session.flush()
            return log

        async with get_db_session() as session:
            result = await session.execute(
                select(ScheduledTask).where(ScheduledTask.id == task_id)
            )
            if result.scalar_one_or_none() is None:
                raise ValueError(f"Task {task_id} not found")
            log = TaskRunLog(
                task_id=task_id,
                status=run_status,
                started_at=now,
                completed_at=now,
                result_summary=result_summary,
                error_message=error_message,
            )
            session.add(log)
            await session.commit()
            await session.refresh(log)
            return log

    async def get_run_history(self, task_id: int, limit: int = 10) -> List[TaskRunLog]:
        """Return recent run logs for a task (most recent first)."""
        stmt = (
            select(TaskRunLog)
            .where(TaskRunLog.task_id == task_id)
            .order_by(TaskRunLog.started_at.desc())
            .limit(limit)
        )

        session = self._session
        if session is not None:
            result = await session.execute(stmt)
            return list(result.scalars().all())

        async with get_db_session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # -- Scheduler queries ----------------------------------------------

    async def get_tasks_due(self) -> List[ScheduledTask]:
        """Return enabled tasks whose next_run_at is in the past (i.e. due now)."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(ScheduledTask)
            .where(
                ScheduledTask.enabled == True,  # noqa: E712
                ScheduledTask.next_run_at.isnot(None),
                ScheduledTask.next_run_at <= now,
            )
            .order_by(ScheduledTask.next_run_at)
        )

        session = self._session
        if session is not None:
            result = await session.execute(stmt)
            return list(result.scalars().all())

        async with get_db_session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())


# -- Module-level singleton access --------------------------------------

_service: Optional[TaskLedgerService] = None


def get_task_ledger_service() -> TaskLedgerService:
    """Get or create the global TaskLedgerService instance."""
    global _service
    if _service is None:
        _service = TaskLedgerService()
    return _service
