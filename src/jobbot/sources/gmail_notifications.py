"""Step 2, `gmail_notifications`: read LinkedIn notification emails and classify
them (spec 0001, AC-2).

These emails usually carry only a snippet, so rules do the cheap work: an obvious
non hiring item is marked `not_job`; a likely hiring post is left `pending` for the
AI parse step, which creates the job and the post author contact.
"""

from __future__ import annotations

import logging
import sqlite3

from .. import gmail_client
from ..config import Settings
from ..repo import raw_items
from ..steps import StepResult
from ..timeutil import now_iso, to_iso
from .linkedin_email import JOB_URL_RE, looks_like_hiring_post

log = logging.getLogger("jobbot.sources.gmail_notifications")

SOURCE = "gmail_notification"


def notification_query(settings: Settings) -> str:
    return (
        f"from:{settings.linkedin_notification_sender} newer_than:{settings.gmail_lookback_days}d"
    )


def _first_post_url(text: str, html: str | None) -> str | None:
    haystack = f"{text}\n{html or ''}"
    match = JOB_URL_RE.search(haystack)
    return match.group(0) if match else None


def run_gmail_notifications(
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
        messages = reader.search(notification_query(settings))
    except gmail_client.GmailReadError as exc:
        return StepResult(ok=False, error=str(exc))

    new_items = not_job = pending = 0
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
        url = _first_post_url(message.text, message.html)
        if looks_like_hiring_post(message.snippet, message.text, url):
            pending += 1
        else:
            raw_items.set_status(conn, raw_id, "not_job", parsed_by="rules")
            not_job += 1

    log.info(
        "gmail_notifications done",
        extra={"messages": len(messages), "new": new_items, "not_job": not_job, "pending": pending},
    )
    return StepResult(
        ok=True,
        summary={
            "messages": len(messages),
            "new": new_items,
            "not_job": not_job,
            "pending": pending,
        },
    )
