from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import SCHEDULE_HOURS, TIMEZONE
from app.database import fetch_one
from app.services.monitor import monitor


scheduler = AsyncIOScheduler(timezone=TIMEZONE)


def most_recent_scheduled_time(now: datetime) -> datetime:
    candidates = [now.replace(hour=hour, minute=0, second=0, microsecond=0) for hour in SCHEDULE_HOURS]
    past = [candidate for candidate in candidates if candidate <= now]
    if past:
        return max(past)
    yesterday = now - timedelta(days=1)
    return yesterday.replace(hour=max(SCHEDULE_HOURS), minute=0, second=0, microsecond=0)


def catch_up_is_needed(now: datetime | None = None) -> bool:
    local_now = now or datetime.now(ZoneInfo(TIMEZONE))
    row = fetch_one(
        """
        SELECT finished_at FROM check_runs
        WHERE status IN ('success', 'partial') AND finished_at IS NOT NULL
        ORDER BY finished_at DESC LIMIT 1
        """
    )
    if not row:
        return True
    last_run = datetime.fromisoformat(row["finished_at"]).astimezone(ZoneInfo(TIMEZONE))
    return last_run < most_recent_scheduled_time(local_now)


async def start_scheduler() -> None:
    scheduler.add_job(
        monitor.run,
        CronTrigger(hour=",".join(str(hour) for hour in SCHEDULE_HOURS), minute=0, timezone=TIMEZONE),
        id="scheduled-job-check",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    if catch_up_is_needed():
        asyncio.create_task(monitor.run())


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

