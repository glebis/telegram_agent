"""
JobQueueBackend — RuntimeScheduler wrapping python-telegram-bot's job_queue.

Dispatches ScheduledJob to run_repeating() or run_daily() based on ScheduleType.
"""

import logging
from typing import Dict, List

from telegram.ext import Application

from .base import RuntimeScheduler, ScheduledJob, ScheduleType

logger = logging.getLogger(__name__)


class JobQueueBackend(RuntimeScheduler):
    """In-process scheduler backed by python-telegram-bot's JobQueue."""

    def __init__(self, application: Application) -> None:
        self._application = application
        self._jobs: Dict[str, ScheduledJob] = {}

    @property
    def _job_queue(self):
        jq = self._application.job_queue
        if jq is None:
            raise RuntimeError("JobQueue not available on this Application")
        return jq

    def schedule(self, job: ScheduledJob) -> None:
        if not job.enabled:
            logger.info("Job '%s' is disabled, skipping", job.name)
            return

        if job.schedule_type == ScheduleType.INTERVAL:
            self._job_queue.run_repeating(
                job.callback,
                interval=job.interval_seconds,
                first=job.first_delay_seconds,
                name=job.name,
            )
            logger.info(
                "Scheduled interval job '%s' every %ds (first after %ds)",
                job.name,
                job.interval_seconds,
                job.first_delay_seconds,
            )

        elif job.schedule_type == ScheduleType.DAILY:
            for t in job.daily_times:
                tag = f"{job.name}_{t.hour}:{t.minute:02d}"
                self._job_queue.run_daily(
                    job.callback,
                    time=t,
                    name=tag,
                )
                logger.info("Scheduled daily job '%s' at %s", job.name, t)

        self._jobs[job.name] = job

    def cancel(self, name: str) -> bool:
        if name not in self._jobs:
            return False

        # Remove all PTB jobs whose name starts with this job name
        removed = False
        for ptb_job in self._job_queue.get_jobs_by_name(name):
            ptb_job.schedule_removal()
            removed = True

        # Also remove daily sub-jobs (name_HH:MM pattern)
        job = self._jobs[name]
        if job.schedule_type == ScheduleType.DAILY:
            for t in job.daily_times:
                tag = f"{name}_{t.hour}:{t.minute:02d}"
                for ptb_job in self._job_queue.get_jobs_by_name(tag):
                    ptb_job.schedule_removal()
                    removed = True

        del self._jobs[name]
        logger.info("Cancelled job '%s'", name)
        return removed

    def list_jobs(self) -> List[str]:
        return list(self._jobs.keys())

    async def start(self) -> None:
        # JobQueue is started by TelegramBot.initialize(), nothing extra needed
        pass

    async def stop(self) -> None:
        for name in list(self._jobs.keys()):
            self.cancel(name)
        logger.info("All scheduled jobs cancelled")
