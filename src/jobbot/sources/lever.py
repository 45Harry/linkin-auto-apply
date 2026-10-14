"""Lever board adapter.

Endpoint confirmed live on 2026-10-14:
    https://api.lever.co/v0/postings/{token}?mode=json
The response is a JSON array; a posting carries `id`, `text` (title),
`categories.location`, `hostedUrl`, `applyUrl`, `createdAt` (epoch milliseconds),
and `descriptionPlain` (the spec's Lever date field is `createdAt`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from .base import AtsPosting, fetch_json

API_BASE = "https://api.lever.co/v0/postings"
TIMEOUT_SECONDS = 30


def _epoch_ms_to_dt(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


class LeverAdapter:
    ats_type = "lever"

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
                params={"mode": "json"},
            )
        finally:
            if self._client is None:
                client.close()

        postings: list[AtsPosting] = []
        for job in payload or []:
            posting_id = job.get("id")
            if not posting_id:
                continue
            hosted_url = job.get("hostedUrl") or f"https://jobs.lever.co/{token}/{posting_id}"
            postings.append(
                AtsPosting(
                    ats_type=self.ats_type,
                    ats_token=token,
                    posting_id=str(posting_id),
                    title=(job.get("text") or "").strip(),
                    location=(job.get("categories") or {}).get("location") or None,
                    canonical_url=hosted_url,
                    description=job.get("descriptionPlain"),
                    posted_at=_epoch_ms_to_dt(job.get("createdAt")),
                    apply_target=job.get("applyUrl") or hosted_url,
                )
            )
        return postings
