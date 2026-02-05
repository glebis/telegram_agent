"""
Scheduled task and run log models for the persistent task ledger.

ScheduledTask: defines a recurring or one-shot scheduled task with context mode.
TaskRunLog: records each execution attempt with status and timing.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ContextMode(str, enum.Enum):
    """Context isolation mode for task execution."""

    SHARED = "shared"
    ISOLATED = "isolated"


class TaskRunStatus(str, enum.Enum):
    """Status of a task run."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ScheduledTask(Base, TimestampMixin):
    """A persistent scheduled task entry in the ledger."""

    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(255), nullable=False)

    # Schedule — exactly one should be set
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    schedule_interval_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    schedule_once_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Execution context
    context_mode: Mapped[ContextMode] = mapped_column(
        Enum(ContextMode), nullable=False, default=ContextMode.ISOLATED
    )

    # State
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    run_logs: Mapped[list["TaskRunLog"]] = relationship(
        "TaskRunLog", back_populates="task", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduledTask(id={self.id}, chat_id={self.chat_id}, "
            f"type={self.task_type}, enabled={self.enabled})>"
        )


class TaskRunLog(Base):
    """Record of a single task execution attempt."""

    __tablename__ = "task_run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scheduled_tasks.id", ondelete="CASCADE"), nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[TaskRunStatus] = mapped_column(Enum(TaskRunStatus), nullable=False)
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    task: Mapped["ScheduledTask"] = relationship(
        "ScheduledTask", back_populates="run_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<TaskRunLog(id={self.id}, task_id={self.task_id}, "
            f"status={self.status})>"
        )
