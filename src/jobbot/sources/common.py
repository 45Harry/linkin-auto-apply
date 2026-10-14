"""Shared helpers that turn parsed data into job rows.

Used by the rules path in the email sources and by the AI path in the parse step,
so both write jobs the same way (AC-5, AC-8).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ..repo import companies
from ..repo import jobs as jobs_repo


def resolve_company_id(conn: sqlite3.Connection, name: str | None) -> int | None:
    """Match a parsed company name to a tracked company; never create one here."""
    if not name or not name.strip():
        return None
    row = companies.find_by_name(conn, name)
    return int(row["id"]) if row else None


def clean_enum(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    if not text or text == "unknown":
        return None
    return text


def clean_int(value: int | None) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def write_parsed_job(
    conn: sqlite3.Connection,
    *,
    source: str,
    dedupe_key: str,
    source_ref: str,
    canonical_url: str | None,
    title: str,
    company: str | None,
    location: str | None,
    work_mode: str | None,
    salary_min: int | None,
    salary_max: int | None,
    salary_currency: str | None,
    seniority: str | None,
    apply_method: str | None,
    apply_target: str | None,
    description: str | None,
    posted_at: datetime,
    posted_at_estimated: int,
    seen_at: str,
    raw_item_id: int | None = None,
) -> tuple[int, bool]:
    from ..timeutil import to_iso

    company_id = resolve_company_id(conn, company)
    return jobs_repo.upsert_parsed_job(
        conn,
        source=source,
        source_ref=source_ref,
        dedupe_key=dedupe_key,
        title=title.strip() or "(untitled)",
        canonical_url=canonical_url,
        company_id=company_id,
        company_name=company,
        location=location,
        work_mode=clean_enum(work_mode),
        salary_min=clean_int(salary_min),
        salary_max=clean_int(salary_max),
        salary_currency=salary_currency,
        seniority=clean_enum(seniority),
        apply_method=clean_enum(apply_method),
        apply_target=apply_target,
        description=description,
        posted_at=to_iso(posted_at),
        posted_at_estimated=posted_at_estimated,
        seen_at=seen_at,
        raw_item_id=raw_item_id,
    )
