"""Source health: the failure and recovery streak (spec 0001, AC-15).

A source is failing after 3 consecutive failed runs and recovered on its first
success. Exactly one alert fires on failing and one on recovery; no repeats in
between, because the transition only happens once.
"""

from __future__ import annotations

import sqlite3
from enum import StrEnum

from .repo import source_health

ALERT_THRESHOLD = 3


class HealthEvent(StrEnum):
    NONE = "none"
    FAILING = "failing"
    RECOVERED = "recovered"


def record_run(
    conn: sqlite3.Connection,
    source: str,
    *,
    ok: bool,
    now: str,
    error: str | None = None,
) -> HealthEvent:
    row = source_health.get(conn, source)
    previous = row["status"] if row else "ok"

    if ok:
        source_health.upsert(
            conn,
            source,
            status="ok",
            last_success_at=now,
            consecutive_failures=0,
        )
        if previous == "failing":
            source_health.upsert(conn, source, alerted_at=now)
            return HealthEvent.RECOVERED
        return HealthEvent.NONE

    failures = (int(row["consecutive_failures"]) if row else 0) + 1
    status = "failing" if failures >= ALERT_THRESHOLD else previous
    source_health.upsert(
        conn,
        source,
        status=status,
        last_error_at=now,
        last_error=error,
        consecutive_failures=failures,
    )
    if failures == ALERT_THRESHOLD and previous != "failing":
        source_health.upsert(conn, source, alerted_at=now)
        return HealthEvent.FAILING
    return HealthEvent.NONE
