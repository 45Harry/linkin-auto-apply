"""Data access and merge logic for the jobs table.

Dedupe and merge (spec 0001, AC-5): an incoming board posting is deduped by
`dedupe_key`, then `canonical_url`, then `match_hash`. A hit adds a sighting and
merges fields; a miss creates a job. Career board data is the top precedence, so
board values always win; sources lower than the board fill nulls only.
"""

from __future__ import annotations

import sqlite3

from ..dedupe import ats_dedupe_key, match_hash
from ..normalize import normalize_url
from ..sources.base import AtsPosting
from ..timeutil import now_iso, parse_iso, to_iso
from . import sightings


def is_older_than(posted_at_iso: str, max_age_days: int) -> bool:
    from datetime import timedelta

    from ..timeutil import now_utc

    return parse_iso(posted_at_iso) < (now_utc() - timedelta(days=max_age_days))


def find_by_dedupe_key(conn: sqlite3.Connection, dedupe_key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM jobs WHERE dedupe_key = ?", (dedupe_key,)).fetchone()


def find_by_canonical_url(conn: sqlite3.Connection, canonical_url: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM jobs WHERE canonical_url = ? ORDER BY id LIMIT 1", (canonical_url,)
    ).fetchone()


def find_by_match_hash(conn: sqlite3.Connection, value: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM jobs WHERE match_hash = ? ORDER BY id LIMIT 1", (value,)
    ).fetchone()


def get(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def set_status(
    conn: sqlite3.Connection, job_id: int, status: str, filter_reason: str | None = None
) -> None:
    conn.execute(
        "UPDATE jobs SET status = ?, filter_reason = ? WHERE id = ?",
        (status, filter_reason, job_id),
    )


def upsert_ats_posting(
    conn: sqlite3.Connection,
    posting: AtsPosting,
    company: sqlite3.Row,
    *,
    seen_at: str,
    max_age_days: int,
) -> tuple[int, bool]:
    dedupe_key = ats_dedupe_key(posting.ats_type, posting.ats_token, posting.posting_id)
    canonical = normalize_url(posting.canonical_url) if posting.canonical_url else None
    value_hash = match_hash(company["name"], posting.title, posting.location)

    existing = find_by_dedupe_key(conn, dedupe_key)
    if existing is None and canonical:
        existing = find_by_canonical_url(conn, canonical)
    if existing is None and value_hash:
        existing = find_by_match_hash(conn, value_hash)

    if existing is None:
        job_id = _create(
            conn,
            posting,
            company_id=int(company["id"]),
            seen_at=seen_at,
            max_age_days=max_age_days,
            dedupe_key=dedupe_key,
            canonical=canonical,
            value_hash=value_hash,
        )
        created = True
    else:
        job_id = int(existing["id"])
        _merge_ats(conn, job_id, posting, company, canonical, value_hash, seen_at)
        created = False

    sightings.ensure(conn, job_id=job_id, source="ats", source_ref=dedupe_key, seen_at=seen_at)
    return job_id, created


def _create(
    conn: sqlite3.Connection,
    posting: AtsPosting,
    *,
    company_id: int,
    seen_at: str,
    max_age_days: int,
    dedupe_key: str,
    canonical: str | None,
    value_hash: str,
) -> int:
    if posting.posted_at is not None:
        posted_at = to_iso(posting.posted_at)
        estimated = 0
    else:
        posted_at = seen_at
        estimated = 1
    status = "expired" if is_older_than(posted_at, max_age_days) else "ready"
    cursor = conn.execute(
        "INSERT INTO jobs ("
        "company_id, title, location, apply_method, apply_target, canonical_url, description, "
        "posted_at, posted_at_estimated, status, dedupe_key, match_hash, missed_polls, "
        "first_seen_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (
            company_id,
            posting.title,
            posting.location,
            posting.apply_method,
            posting.apply_target,
            canonical,
            posting.description,
            posted_at,
            estimated,
            status,
            dedupe_key,
            value_hash,
            seen_at,
            seen_at,
        ),
    )
    return int(cursor.lastrowid)


def _merge_ats(
    conn: sqlite3.Connection,
    job_id: int,
    posting: AtsPosting,
    company: sqlite3.Row,
    canonical: str | None,
    value_hash: str,
    seen_at: str,
) -> None:
    values: dict[str, object] = {
        "company_id": int(company["id"]),
        "title": posting.title,
        "location": posting.location,
        "apply_method": posting.apply_method,
        "apply_target": posting.apply_target,
        "canonical_url": canonical,
        "description": posting.description,
        "match_hash": value_hash,
        "last_seen_at": seen_at,
        "missed_polls": 0,
    }
    if posting.posted_at is not None:
        values["posted_at"] = to_iso(posting.posted_at)
        values["posted_at_estimated"] = 0
    assignments = ", ".join(f"{column} = ?" for column in values)
    conn.execute(
        f"UPDATE jobs SET {assignments} WHERE id = ?",
        [*values.values(), job_id],
    )


def sweep_missed_polls(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    seen_keys: set[str],
    threshold: int = 3,
) -> int:
    """Increment `missed_polls` for board jobs not seen this run; expire at the threshold.

    A job counts as seen when any of its board sightings was seen this run, so a
    job fed by several postings (merged by match hash) is never falsely expired.
    """
    seen_job_ids: set[int] = set()
    if seen_keys:
        placeholders = ", ".join("?" for _ in seen_keys)
        rows = conn.execute(
            f"SELECT DISTINCT job_id FROM sightings WHERE source = 'ats' "
            f"AND source_ref IN ({placeholders})",
            list(seen_keys),
        ).fetchall()
        seen_job_ids = {int(row["job_id"]) for row in rows}

    rows = conn.execute(
        "SELECT id, missed_polls, status FROM jobs "
        "WHERE company_id = ? AND EXISTS ("
        "  SELECT 1 FROM sightings WHERE job_id = jobs.id AND source = 'ats')",
        (company_id,),
    ).fetchall()
    expired = 0
    for row in rows:
        if int(row["id"]) in seen_job_ids:
            if int(row["missed_polls"]) != 0:
                conn.execute("UPDATE jobs SET missed_polls = 0 WHERE id = ?", (row["id"],))
            continue
        missed = int(row["missed_polls"]) + 1
        if missed >= threshold and row["status"] not in ("expired", "filtered"):
            conn.execute(
                "UPDATE jobs SET missed_polls = ?, status = 'expired' WHERE id = ?",
                (missed, row["id"]),
            )
            expired += 1
        else:
            conn.execute("UPDATE jobs SET missed_polls = ? WHERE id = ?", (missed, row["id"]))
    return expired


def upsert_parsed_job(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_ref: str,
    dedupe_key: str,
    title: str,
    canonical_url: str | None,
    company_id: int | None,
    company_name: str | None,
    location: str | None,
    work_mode: str | None,
    salary_min: int | None,
    salary_max: int | None,
    salary_currency: str | None,
    seniority: str | None,
    apply_method: str | None,
    apply_target: str | None,
    description: str | None,
    posted_at: str,
    posted_at_estimated: int,
    seen_at: str,
    raw_item_id: int | None = None,
) -> tuple[int, bool]:
    """Upsert a job parsed from an email, post, or search result (AC-1, AC-2, AC-5).

    Lookup is `dedupe_key`, then `canonical_url`, then `match_hash` when a company
    is known. A new job is created `new` (the filter pass sets `ready` or `expired`);
    a hit adds a sighting and fills only fields that are still null.
    """
    canonical = normalize_url(canonical_url) if canonical_url else None
    value_hash = match_hash(company_name, title, location) if company_name else None

    existing = find_by_dedupe_key(conn, dedupe_key)
    if existing is None and canonical:
        existing = find_by_canonical_url(conn, canonical)
    if existing is None and value_hash:
        existing = find_by_match_hash(conn, value_hash)

    if existing is None:
        cursor = conn.execute(
            "INSERT INTO jobs ("
            "company_id, title, location, work_mode, salary_min, salary_max, salary_currency, "
            "seniority, apply_method, apply_target, canonical_url, description, posted_at, "
            "posted_at_estimated, status, dedupe_key, match_hash, missed_polls, "
            "first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, 0, ?, ?)",
            (
                company_id,
                title,
                location,
                work_mode,
                salary_min,
                salary_max,
                salary_currency,
                seniority,
                apply_method,
                apply_target,
                canonical,
                description,
                posted_at,
                posted_at_estimated,
                dedupe_key,
                value_hash,
                seen_at,
                seen_at,
            ),
        )
        job_id = int(cursor.lastrowid)
        created = True
    else:
        job_id = int(existing["id"])
        conn.execute(
            "UPDATE jobs SET "
            "company_id = COALESCE(company_id, ?), title = COALESCE(title, ?), "
            "location = COALESCE(location, ?), work_mode = COALESCE(work_mode, ?), "
            "salary_min = COALESCE(salary_min, ?), salary_max = COALESCE(salary_max, ?), "
            "salary_currency = COALESCE(salary_currency, ?), seniority = COALESCE(seniority, ?), "
            "apply_method = COALESCE(apply_method, ?), apply_target = COALESCE(apply_target, ?), "
            "canonical_url = COALESCE(canonical_url, ?), description = COALESCE(description, ?), "
            "match_hash = COALESCE(match_hash, ?), last_seen_at = ? "
            "WHERE id = ?",
            (
                company_id,
                title,
                location,
                work_mode,
                salary_min,
                salary_max,
                salary_currency,
                seniority,
                apply_method,
                apply_target,
                canonical,
                description,
                value_hash,
                seen_at,
                job_id,
            ),
        )
        created = False

    sightings.ensure(
        conn,
        job_id=job_id,
        source=source,
        source_ref=source_ref,
        seen_at=seen_at,
        raw_item_id=raw_item_id,
    )
    return job_id, created


def touch_last_seen(conn: sqlite3.Connection, job_id: int, seen_at: str) -> None:
    conn.execute(
        "UPDATE jobs SET last_seen_at = ? WHERE id = ?",
        (seen_at or now_iso(), job_id),
    )


def counts_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
    return {row["status"]: int(row["n"]) for row in rows}
