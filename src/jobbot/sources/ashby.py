"""Ashby board adapter.

Endpoint confirmed live on 2026-10-14:
    https://api.ashbyhq.com/posting-api/job-board/{token}
The response is `{"jobs": [...]}`; a posting carries `id`, `title`, `location`,
`jobUrl`, `applyUrl`, `publishedAt` (ISO 8601, the spec's Ashby date field),
`isListed`, and `descriptionHtml`.
"""

from __future__ import annotations

import httpx

from .base import AtsPosting, fetch_json

API_BASE = "https://api.ashbyhq.com/posting-api/job-board"
TIMEOUT_SECONDS = 30


class AshbyAdapter:
    ats_type = "ashby"

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
            )
        finally:
            if self._client is None:
                client.close()

        postings: list[AtsPosting] = []
        for job in (payload or {}).get("jobs", []):
            if job.get("isListed") is False:
                continue
            posting_id = job.get("id")
            if not posting_id:
                continue
            job_url = job.get("jobUrl") or f"https://jobs.ashbyhq.com/{token}/{posting_id}"
            postings.append(
                AtsPosting(
                    ats_type=self.ats_type,
                    ats_token=token,
                    posting_id=str(posting_id),
                    title=(job.get("title") or "").strip(),
                    location=job.get("location") or None,
                    canonical_url=job_url,
                    description=job.get("descriptionHtml"),
                    posted_at=job.get("publishedAt"),
                    apply_target=job.get("applyUrl") or job_url,
                )
            )
        return postings
