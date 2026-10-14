"""One long running process: run the hourly cycle at start, then every hour.

`max_instances=1` and `coalesce=True` keep the cycle from overlapping itself
(spec 0001 key invariants). The profile refresh is its own job so it can run
independently of the cycle; it is idempotent and checks its inputs by hash.
"""

from __future__ import annotations

import logging
import sqlite3

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import Settings
from .cycle import hourly_cycle
from .profile import run_profile_refresh

log = logging.getLogger("jobbot.scheduler")

HOURLY_JOB_ID = "hourly_cycle"
PROFILE_JOB_ID = "profile_refresh"


def run_scheduler(conn: sqlite3.Connection, settings: Settings) -> None:
    scheduler = BlockingScheduler(timezone=settings.tz)
    scheduler.add_job(
        hourly_cycle,
        trigger=IntervalTrigger(hours=1),
        args=[conn, settings],
        id=HOURLY_JOB_ID,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        run_profile_refresh,
        trigger=IntervalTrigger(hours=1),
        args=[conn, settings],
        id=PROFILE_JOB_ID,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    log.info("running first cycle at startup")
    hourly_cycle(conn, settings)
    log.info("running first profile refresh at startup")
    _run_startup_profile(conn, settings)
    log.info("scheduler started", extra={"timezone": settings.tz})
    scheduler.start()


def _run_startup_profile(conn: sqlite3.Connection, settings: Settings) -> None:
    try:
        run_profile_refresh(conn, settings)
    except Exception:  # noqa: BLE001 - a startup failure must not stop the scheduler
        log.exception("profile refresh failed at startup")
