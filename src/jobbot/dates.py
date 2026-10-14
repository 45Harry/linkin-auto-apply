"""Date helpers for the AC-6 order.

A LinkedIn post's activity id holds a millisecond timestamp in its top 41 bits, so
`posted_at = (id >> 22)` ms since 1970, and it is exact. Relative text ("1w",
"3 days ago") is converted against the source's own timestamp.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from .timeutil import parse_iso

_ACTIVITY_IN_URL = re.compile(r"(?:activity[-:/]|urn:li:activity:)(\d{10,25})", re.IGNORECASE)
_RELATIVE = re.compile(
    r"(\d+)\s*"
    r"(mo|mins?|minutes?|yr|years?|w|weeks?|d|days?|h|hours?|m)\b",
    re.IGNORECASE,
)
_UNIT_SECONDS = {
    "mo": 30 * 86400,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "yr": 365 * 86400,
    "year": 365 * 86400,
    "years": 365 * 86400,
    "w": 7 * 86400,
    "week": 7 * 86400,
    "weeks": 7 * 86400,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "h": 3600,
    "hour": 3600,
    "hours": 3600,
    "m": 60,
}


def activity_id(text: str | None) -> str | None:
    if not text:
        return None
    match = _ACTIVITY_IN_URL.search(text)
    return match.group(1) if match else None


def activity_timestamp(value: str | int) -> datetime:
    return datetime.fromtimestamp((int(value) >> 22) / 1000, tz=UTC)


def parse_relative(text: str | None) -> timedelta | None:
    if not text:
        return None
    match = _RELATIVE.search(text)
    if not match:
        return None
    seconds = _UNIT_SECONDS.get(match.group(2).lower())
    if seconds is None:
        return None
    return timedelta(seconds=int(match.group(1)) * seconds)


def choose_posted_at(
    *,
    exact: datetime | None = None,
    search_date: datetime | None = None,
    relative: timedelta | None = None,
    source_ts: datetime | None = None,
    first_seen: datetime,
) -> tuple[datetime, int]:
    """Return `(posted_at, posted_at_estimated)` in the AC-6 order.

    The exact date and the search result's own date are not estimated; every
    fallback after them is.
    """
    if exact is not None:
        return exact, 0
    if search_date is not None:
        return search_date, 0
    if relative is not None:
        base = source_ts or first_seen
        return base - relative, 1
    if source_ts is not None:
        return source_ts, 1
    return first_seen, 1


def parse_iso_or_none(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parse_iso(value)
    except ValueError:
        return None
