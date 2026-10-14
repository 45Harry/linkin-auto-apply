"""The light filter (spec 0001, AC-7).

Sets `filtered` with a `filter_reason` for an exclude keyword matched case
insensitively on whole words in the title or company name, and promotes every
other parsed job within 14 days to `ready`. Age is handled only by `expired`
(AC-6): a `new` or `ready` job older than the window becomes `expired`.
"""

from __future__ import annotations

import re
import sqlite3

from .repo import jobs as jobs_repo

NOT_HIRING = "not_hiring"
EXCLUDE_KEYWORD = "exclude_keyword"


def match_exclude_keyword(
    title: str | None, company_name: str | None, keywords: list[str]
) -> str | None:
    for keyword in keywords:
        term = keyword.strip()
        if not term:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
        for text in (title or "", company_name or ""):
            if pattern.search(text):
                return term
    return None


def light_filter(
    conn: sqlite3.Connection,
    *,
    now_iso: str,
    max_age_days: int,
    exclude_keywords: list[str],
    not_hiring_job_ids: set[int] | None = None,
) -> dict[str, int]:
    not_hiring_job_ids = not_hiring_job_ids or set()
    rows = conn.execute(
        "SELECT j.id, j.title, j.status, j.posted_at, c.name AS company_name "
        "FROM jobs j LEFT JOIN companies c ON c.id = j.company_id "
        "WHERE j.status IN ('new', 'ready') ORDER BY j.id"
    ).fetchall()

    expired = filtered = ready = 0
    for row in rows:
        job_id = int(row["id"])
        if jobs_repo.is_older_than(row["posted_at"], max_age_days):
            if row["status"] != "expired":
                jobs_repo.set_status(conn, job_id, "expired")
                expired += 1
            continue
        if row["status"] != "new":
            continue
        if job_id in not_hiring_job_ids:
            jobs_repo.set_status(conn, job_id, "filtered", NOT_HIRING)
            filtered += 1
            continue
        keyword = match_exclude_keyword(row["title"], row["company_name"], exclude_keywords)
        if keyword is not None:
            jobs_repo.set_status(conn, job_id, "filtered", EXCLUDE_KEYWORD)
            filtered += 1
            continue
        jobs_repo.set_status(conn, job_id, "ready")
        ready += 1

    return {"expired": expired, "filtered": filtered, "ready": ready}


def expire_old_ready(conn: sqlite3.Connection, *, now_iso: str, max_age_days: int) -> int:
    """Expire any `new` or `ready` job whose `posted_at` is past the window (AC-6)."""
    rows = conn.execute(
        "SELECT id, posted_at FROM jobs WHERE status IN ('new', 'ready')"
    ).fetchall()
    expired = 0
    for row in rows:
        if jobs_repo.is_older_than(row["posted_at"], max_age_days):
            jobs_repo.set_status(conn, int(row["id"]), "expired")
            expired += 1
    return expired
