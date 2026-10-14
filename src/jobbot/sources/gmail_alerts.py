"""Step 1, `gmail_alerts`: read LinkedIn job alert emails and extract jobs
(spec 0001, AC-1, AC-8).

The query reads every result page for the last 15 days. Each email becomes a raw
item. Rules based extraction reads the structured alert HTML; when it cannot read
a title, company, and location for every posting, the item is left `pending` for
the AI parse step.
"""

from __future__ import annotations

import logging
import sqlite3

from .. import gmail_client
from ..config import Settings
from ..dates import choose_posted_at
from ..db import transaction
from ..dedupe import linkedin_job_key
from ..repo import raw_items
from ..steps import StepResult
from ..timeutil import now_iso, parse_iso, to_iso
from .common import write_parsed_job
from .linkedin_email import extract_alert_postings

log = logging.getLogger("jobbot.sources.gmail_alerts")

SOURCE = "gmail_alert"


def alert_query(settings: Settings) -> str:
    senders = [item.strip() for item in settings.linkedin_alert_senders.split(",") if item.strip()]
    sender_clause = " OR ".join(senders) if senders else "jobalerts-noreply@linkedin.com"
    return f"from:({sender_clause}) newer_than:{settings.gmail_lookback_days}d"


def run_gmail_alerts(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    seen_at: str | None = None,
    reader: gmail_client.GmailReader | None = None,
) -> StepResult:
    seen_at = seen_at or now_iso()
    if reader is None:
        creds = gmail_client.load_credentials(settings.resolved_gmail_token_file)
        if creds is None:
            return StepResult(ok=False, error="gmail token missing or revoked")
        reader = gmail_client.ApiGmailReader(creds)

    try:
        messages = reader.search(alert_query(settings))
    except gmail_client.GmailReadError as exc:
        return StepResult(ok=False, error=str(exc))

    new_items = jobs_created = pending = 0
    for message in messages:
        content = message.html or message.text or message.snippet
        raw_id, is_new = raw_items.upsert(
            conn,
            source=SOURCE,
            external_id=message.id,
            content=content,
            fetched_at=to_iso(message.internal_date),
        )
        if not is_new:
            continue
        new_items += 1
        postings = extract_alert_postings(message.html, message.text)
        if not postings:
            pending += 1
            continue
        with transaction(conn):
            for posting in postings:
                posted_at, estimated = choose_posted_at(
                    source_ts=message.internal_date,
                    first_seen=parse_iso(seen_at),
                )
                _, was_created = write_parsed_job(
                    conn,
                    source=SOURCE,
                    dedupe_key=linkedin_job_key(posting.job_id),
                    source_ref=linkedin_job_key(posting.job_id),
                    canonical_url=posting.url,
                    title=posting.title,
                    company=posting.company,
                    location=posting.location,
                    work_mode=None,
                    salary_min=None,
                    salary_max=None,
                    salary_currency=None,
                    seniority=None,
                    apply_method=None,
                    apply_target=posting.url,
                    description=None,
                    posted_at=posted_at,
                    posted_at_estimated=estimated,
                    seen_at=seen_at,
                    raw_item_id=raw_id,
                )
                jobs_created += int(was_created)
            raw_items.set_status(conn, raw_id, "parsed", parsed_by="rules")

    log.info(
        "gmail_alerts done",
        extra={
            "messages": len(messages),
            "new": new_items,
            "jobs": jobs_created,
            "pending": pending,
        },
    )
    return StepResult(
        ok=True,
        summary={
            "messages": len(messages),
            "new": new_items,
            "jobs": jobs_created,
            "pending": pending,
        },
    )
