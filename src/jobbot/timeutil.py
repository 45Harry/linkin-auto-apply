"""Small time helpers. Timestamps are stored as ISO 8601 UTC strings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def now_iso() -> str:
    return to_iso(now_utc())


def days_ago(days: int) -> datetime:
    return now_utc() - timedelta(days=days)


def local_date(now: datetime, tz: str) -> str:
    """The calendar date in the configured timezone, as `YYYY-MM-DD`."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d")


def local_today(tz: str) -> str:
    return local_date(now_utc(), tz)


def local_date_of(iso: str, tz: str) -> str:
    return local_date(parse_iso(iso), tz)
