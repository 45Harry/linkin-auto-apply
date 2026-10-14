"""Workable board adapter.

Endpoint confirmed live on 2026-10-14:
    https://apply.workable.com/api/v1/widget/accounts/{token}?details=true
The response is `{"name", "description", "jobs": [...]}`; a posting carries
`shortcode` (the id), `title`, `locations` (an array of `{city, region, country,
hidden}`, so multi-location postings are not lost), `url`, `application_url`,
`published_on` (a `YYYY-MM-DD` date, the spec's Workable date field), and
`description` (HTML).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from .base import AtsPosting, fetch_json

API_BASE = "https://apply.workable.com/api/v1/widget/accounts"
TIMEOUT_SECONDS = 30


def _date_to_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _workable_location(job: dict) -> str | None:
    parts: list[str] = []
    for loc in job.get("locations") or []:
        if loc.get("hidden"):
            continue
        bits = [loc.get("city"), loc.get("region"), loc.get("country")]
        text = ", ".join(part for part in bits if part)
        if text:
            parts.append(text)
    if parts:
        return " | ".join(parts)
    fallback = [job.get("city"), job.get("state"), job.get("country")]
    text = ", ".join(part for part in fallback if part)
    return text or None


class WorkableAdapter:
    ats_type = "workable"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, token: str) -> list[AtsPosting]:
        client = self._client or httpx.Client(timeout=TIMEOUT_SECONDS)
        try:
            payload = fetch_json(
                client,
                f"{API_BASE}/{token}",
                ats_type=self.ats_type,
                token=token,
                params={"details": "true"},
            )
        finally:
            if self._client is None:
                client.close()

        postings: list[AtsPosting] = []
        for job in (payload or {}).get("jobs", []):
            posting_id = job.get("shortcode") or job.get("id")
            if not posting_id:
                continue
            url = job.get("url") or job.get("shortlink")
            postings.append(
                AtsPosting(
                    ats_type=self.ats_type,
                    ats_token=token,
                    posting_id=str(posting_id),
                    title=(job.get("title") or "").strip(),
                    location=_workable_location(job),
                    canonical_url=url or f"https://apply.workable.com/j/{posting_id}",
                    description=job.get("description"),
                    posted_at=_date_to_dt(job.get("published_on") or job.get("created_at")),
                    apply_target=job.get("application_url") or url,
                )
            )
        return postings
