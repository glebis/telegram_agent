"""
Scheduler base types and abstract interface.

ScheduleType / ScheduledJob define what to run and when.
RuntimeScheduler is the ABC for in-process backends (e.g. JobQueueBackend).
"""

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import time
from typing import Any, Callable, Coroutine, List, Optional


class ScheduleType(enum.Enum):
    INTERVAL = "interval"
    DAILY = "daily"


@dataclass
class ScheduledJob:
    """Describes a job to be scheduled."""

    name: str
    callback: Callable[..., Coroutine[Any, Any, None]]
    schedule_type: ScheduleType
    interval_seconds: Optional[int] = None
    daily_times: List[time] = field(default_factory=list)
    enabled: bool = True
    first_delay_seconds: int = 60

    def __post_init__(self) -> None:
        if self.schedule_type == ScheduleType.INTERVAL and not self.interval_seconds:
            raise ValueError("interval_seconds required for INTERVAL schedule")
        if self.schedule_type == ScheduleType.DAILY and not self.daily_times:
            raise ValueError("daily_times required for DAILY schedule")


class RuntimeScheduler(ABC):
    """ABC for in-process job schedulers."""

    @abstractmethod
    def schedule(self, job: ScheduledJob) -> None:
        """Register a job for execution."""

    @abstractmethod
    def cancel(self, name: str) -> bool:
        """Cancel a scheduled job by name. Returns True if found."""

    @abstractmethod
    def list_jobs(self) -> List[str]:
        """Return names of all registered jobs."""

    @abstractmethod
    async def start(self) -> None:
        """Start the scheduler (if needed beyond registration)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the scheduler and cancel all jobs."""
