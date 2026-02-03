"""
Scheduler abstraction for periodic tasks.

Provides:
- RuntimeScheduler ABC for in-process job execution
- JobQueueBackend wrapping python-telegram-bot's job_queue
- Install generators for OS-level scheduling (launchd/systemd/cron)
"""

from .base import RuntimeScheduler, ScheduledJob, ScheduleType
from .job_queue_backend import JobQueueBackend

__all__ = [
    "RuntimeScheduler",
    "ScheduledJob",
    "ScheduleType",
    "JobQueueBackend",
]
