"""Step 5, `parse_pending`: run the AI parser over pending raw items (spec 0001,
AC-1, AC-2, AC-6, AC-8, AC-9, AC-10).

Items are parsed by source: alerts as a job list, notifications as a single post.
An item that fails every provider stays `pending` and is retried next run until it
ages past 14 days, at which point it is marked `failed`.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import timedelta

from .ai.router import AiRouter
from .ai.schemas import ParsedJobList, ParsedPost
from .config import Settings
from .dates import (
    activity_id,
    activity_timestamp,
    choose_posted_at,
    parse_iso_or_none,
    parse_relative,
)
from .db import transaction
from .dedupe import linkedin_job_key, linkedin_post_key, url_dedupe_key
from .repo import contacts, raw_items
from .sources.common import write_parsed_job
from .sources.linkedin_email import JOB_ID_RE
from .steps import StepResult
from .text_extract import find_email, find_linkedin_profile, find_phone
from .timeutil import now_iso, now_utc, parse_iso, to_iso

log = logging.getLogger("jobbot.parse")

ALERT = "gmail_alert"
NOTIFICATION = "gmail_notification"


def _dates_from_text(value: str | None) -> tuple[object, object]:
    if not value:
        return None, None
    exact = parse_iso_or_none(value)
    if exact is not None:
        return exact, None
    return None, parse_relative(value)


def run_parse_pending(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    seen_at: str | None = None,
    router: AiRouter | None = None,
) -> StepResult:
    seen_at = seen_at or now_iso()
    cutoff_iso = to_iso(now_utc() - timedelta(days=settings.max_job_age_days))
    aged_out = raw_items.fail_too_old(conn, cutoff_iso=cutoff_iso)

    router = router or AiRouter(settings, conn)
    rows = raw_items.list_pending(conn, min_fetched_at=cutoff_iso)
    parsed = not_job = failed = 0
    for row in rows:
        source = row["source"]
        try:
            if source == ALERT:
                outcome = _parse_alert(conn, row, router, seen_at)
            elif source == NOTIFICATION:
                outcome = _parse_notification(conn, row, router, seen_at)
            else:
                continue
        except Exception as exc:  # noqa: BLE001 - one item must not stop the step
            log.exception("parse item failed", extra={"raw_item_id": row["id"], "error": str(exc)})
            raw_items.set_status(conn, int(row["id"]), "pending", error=str(exc))
            failed += 1
            continue
        parsed += int(outcome == "parsed")
        not_job += int(outcome == "not_job")
        failed += int(outcome == "failed")

    log.info(
        "parse_pending done",
        extra={
            "pending": len(rows),
            "parsed": parsed,
            "not_job": not_job,
            "failed": failed,
            "aged_out": aged_out,
        },
    )
    return StepResult(
        ok=True,
        summary={
            "pending": len(rows),
            "parsed": parsed,
            "not_job": not_job,
            "failed": failed,
            "aged_out": aged_out,
        },
    )


def _parse_alert(conn: sqlite3.Connection, row: sqlite3.Row, router: AiRouter, seen_at: str) -> str:
    raw_id = int(row["id"])
    model, provider = router.parse(
        user=f"Source: LinkedIn job alert email.\n\n{row['content']}", model_cls=ParsedJobList
    )
    if model is None:
        return "failed"
    source_ts = parse_iso(row["fetched_at"])
    jobs_created = 0
    with transaction(conn):
        for job in model.jobs:
            if not job.is_job or not (job.title or job.url):
                continue
            url_match = JOB_ID_RE.search(job.url or "") if job.url else None
            if url_match:
                dedupe = linkedin_job_key(url_match.group(1))
            else:
                dedupe = url_dedupe_key(job.url or job.apply_target or job.title)
            exact, relative = _dates_from_text(job.posted_at)
            posted_at, estimated = choose_posted_at(
                exact=exact,
                relative=relative,
                source_ts=source_ts,
                first_seen=parse_iso(seen_at),
            )
            _, was_created = write_parsed_job(
                conn,
                source=ALERT,
                dedupe_key=dedupe,
                source_ref=dedupe,
                canonical_url=job.url,
                title=job.title or "(untitled)",
                company=job.company,
                location=job.location,
                work_mode=job.work_mode,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency=job.salary_currency,
                seniority=job.seniority,
                apply_method=job.apply_method,
                apply_target=job.apply_target or job.url,
                description=job.description,
                posted_at=posted_at,
                posted_at_estimated=estimated,
                seen_at=seen_at,
                raw_item_id=raw_id,
            )
            jobs_created += int(was_created)
        raw_items.set_status(conn, raw_id, "parsed", parsed_by=provider)
    log.info(
        "alert parsed", extra={"raw_item_id": raw_id, "provider": provider, "jobs": jobs_created}
    )
    return "parsed"


def _parse_notification(
    conn: sqlite3.Connection, row: sqlite3.Row, router: AiRouter, seen_at: str
) -> str:
    raw_id = int(row["id"])
    content = row["content"]
    model, provider = router.parse(
        user=f"Source: LinkedIn notification email.\n\n{content}", model_cls=ParsedPost
    )
    if model is None:
        return "failed"
    if not model.is_hiring_post:
        raw_items.set_status(conn, raw_id, "not_job", parsed_by=provider)
        return "not_job"

    source_ts = parse_iso(row["fetched_at"])
    activity = model.activity_id or activity_id(content)
    exact = activity_timestamp(activity) if activity else None
    relative = None
    if exact is None:
        _, relative = _dates_from_text(model.posted_at)
    posted_at, estimated = choose_posted_at(
        exact=exact,
        relative=relative,
        source_ts=source_ts,
        first_seen=parse_iso(seen_at),
    )

    if activity:
        dedupe = linkedin_post_key(activity)
    else:
        dedupe = url_dedupe_key(model.job_url or content)

    email = find_email(content)
    if email is None and model.contact_email and model.contact_email in content:
        email = model.contact_email
    phone = find_phone(content)
    author_url = find_linkedin_profile(content)
    author_name = (model.author_name or "").strip()

    with transaction(conn):
        job_id, was_created = write_parsed_job(
            conn,
            source=NOTIFICATION,
            dedupe_key=dedupe,
            source_ref=dedupe,
            canonical_url=model.job_url,
            title=(model.title or author_name or "Hiring post"),
            company=model.company,
            location=model.location,
            work_mode=None,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            seniority=None,
            apply_method="email" if email else None,
            apply_target=email or model.job_url,
            description=content,
            posted_at=posted_at,
            posted_at_estimated=estimated,
            seen_at=seen_at,
            raw_item_id=raw_id,
        )
        if author_name:
            contacts.ensure(
                conn,
                job_id=job_id,
                name=author_name,
                role="post_author",
                linkedin_url=author_url,
                email=email,
                phone=phone,
            )
        raw_items.set_status(conn, raw_id, "parsed", parsed_by=provider)
    log.info(
        "notification parsed",
        extra={"raw_item_id": raw_id, "provider": provider, "created": was_created},
    )
    return "parsed"
