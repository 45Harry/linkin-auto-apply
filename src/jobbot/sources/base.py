"""The board source contract and its validated posting shape."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field


class AtsPosting(BaseModel):
    """One posting read from a public career board, already validated."""

    ats_type: str
    ats_token: str
    posting_id: str
    title: str
    location: str | None = None
    canonical_url: str
    description: str | None = None
    posted_at: datetime | None = None
    company_name: str | None = None
    apply_method: str = "ats_form"
    apply_target: str | None = None


class BoardError(Exception):
    """A board could not be fetched. `dead` marks a permanent missing board."""

    def __init__(self, message: str, *, dead: bool = False) -> None:
        super().__init__(message)
        self.dead = dead


def fetch_json(
    client: httpx.Client,
    url: str,
    *,
    ats_type: str,
    token: str,
    params: dict[str, str] | None = None,
) -> Any:
    """GET a board and return its JSON, mapping failures to `BoardError`.

    A 404 means the board is gone (`dead=True`, so the caller counts it toward
    the death threshold); anything else is a transient error (`dead=False`).
    """
    try:
        response = client.get(url, params=params)
        if response.status_code == 404:
            raise BoardError(f"{ats_type} board {token} not found", dead=True)
        response.raise_for_status()
        return response.json()
    except BoardError:
        raise
    except httpx.HTTPError as exc:
        raise BoardError(f"{ats_type} board {token} fetch failed: {exc}") from exc


class BoardAdapter(Protocol):
    ats_type: str

    def fetch(self, token: str) -> list[AtsPosting]: ...


class FetchOutcome(BaseModel):
    token: str
    postings: list[AtsPosting] = Field(default_factory=list)
    error: str | None = None
    dead: bool = False
