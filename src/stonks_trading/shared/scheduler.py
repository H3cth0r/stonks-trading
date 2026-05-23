"""Scheduler for periodic tasks.

APScheduler wrapper for daily retraining and genome hot-swap.
Runs at 00:00 UTC every day.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class Scheduler:
    """APScheduler wrapper for periodic tasks.

    Manages daily retraining schedule at 00:00 UTC and
    other periodic tasks like status updates.
    """

    def __init__(self):
        """Initialize scheduler."""
        self._scheduler = AsyncIOScheduler()
        self._running = False

    def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        self._scheduler.start()
        self._running = True
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._running:
            return

        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Scheduler stopped")

    def schedule_daily_retrain(
        self,
        callback: callable,
        hour: int = 0,
        minute: int = 0,
        timezone: str = "UTC",
    ) -> None:
        """Schedule daily retraining task.

        Args:
            callback: Async function to call for retraining
            hour: Hour to run (default 0 = midnight)
            minute: Minute to run (default 0)
            timezone: Timezone for cron (default UTC)
        """
        trigger = CronTrigger(hour=hour, minute=minute, timezone=timezone)
        self._scheduler.add_job(
            callback,
            trigger=trigger,
            id="daily_retrain",
            name="Daily NEAT Retraining",
            replace_existing=True,
        )
        logger.info(f"Scheduled daily retrain at {hour:02d}:{minute:02d} {timezone}")

    def schedule_interval(
        self,
        callback: callable,
        minutes: int | None = None,
        hours: int | None = None,
        seconds: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Schedule task at interval.

        Args:
            callback: Async function to call
            minutes: Interval in minutes
            hours: Interval in hours
            seconds: Interval in seconds
            **kwargs: Additional arguments for scheduler

        Returns:
            Job ID
        """
        interval = kwargs.pop("interval", None)
        if interval:
            unit = kwargs.pop("unit", "minutes")
            job = self._scheduler.add_job(
                callback,
                "interval",
                **{unit: interval, **kwargs},
            )
        elif minutes:
            job = self._scheduler.add_job(
                callback,
                "interval",
                minutes=minutes,
                **kwargs,
            )
        elif hours:
            job = self._scheduler.add_job(
                callback,
                "interval",
                hours=hours,
                **kwargs,
            )
        elif seconds:
            job = self._scheduler.add_job(
                callback,
                "interval",
                seconds=seconds,
                **kwargs,
            )
        else:
            raise ValueError("Must specify interval in minutes, hours, or seconds")

        return job.id

    def remove_job(self, job_id: str) -> None:
        """Remove a scheduled job.

        Args:
            job_id: ID of job to remove
        """
        self._scheduler.remove_job(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs.

        Returns:
            List of job info dicts
        """
        jobs = self._scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in jobs
        ]

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running