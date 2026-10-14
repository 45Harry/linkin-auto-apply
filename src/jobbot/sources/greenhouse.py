"""Greenhouse board adapter.

Endpoint confirmed live on 2026-10-14:
    https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
A posting carries `id`, `title`, `location.name`, `absolute_url`,
`first_published`, and `content` (HTML).
"""

from __future__ import annotations

import httpx

from .base import AtsPosting, fetch_json

API_BASE = "https://boards-api.greenhouse.io/v1/boards"
TIMEOUT_SECONDS = 30


class GreenhouseAdapter:
    ats_type = "greenhouse"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, token: str) -> list[AtsPosting]:
        client = self._client or httpx.Client(timeout=TIMEOUT_SECONDS)
        try:
            payload = fetch_json(
                client,
                f"{API_BASE}/{token}/jobs",
                ats_type=self.ats_type,
                token=token,
                params={"content": "true"},
            )
        finally:
            if self._client is None:
                client.close()

        postings: list[AtsPosting] = []
        for job in payload.get("jobs", []):
            location = job.get("location") or {}
            postings.append(
                AtsPosting(
                    ats_type=self.ats_type,
                    ats_token=token,
                    posting_id=str(job["id"]),
                    title=job.get("title", "").strip(),
                    location=(location.get("name") or None),
                    canonical_url=job.get("absolute_url") or f"{API_BASE}/{token}/jobs/{job['id']}",
                    description=job.get("content"),
                    posted_at=job.get("first_published") or job.get("updated_at"),
                    company_name=job.get("company_name"),
                    apply_target=job.get("absolute_url"),
                )
            )
        return postings
