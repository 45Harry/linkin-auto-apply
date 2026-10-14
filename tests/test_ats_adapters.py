"""Tests for the Lever, Ashby, and Workable board adapters (spec 0001, AC-3).

Endpoints were confirmed live on 2026-10-14; these tests use a fake HTTP client
so nothing touches the network.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from jobbot.cycle import _adapters
from jobbot.sources.ashby import AshbyAdapter
from jobbot.sources.base import BoardError
from jobbot.sources.greenhouse import GreenhouseAdapter
from jobbot.sources.lever import LeverAdapter
from jobbot.sources.workable import WorkableAdapter


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("GET", "http://test"), response=self
            )

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self, response: object = None, *, raises: Exception | None = None) -> None:
        self._response = response
        self._raises = raises
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url: str, params: dict | None = None) -> object:
        self.calls.append((url, params))
        if self._raises is not None:
            raise self._raises
        return self._response

    def close(self) -> None:
        pass


def test_adapters_are_registered():
    assert set(_adapters()) == {"greenhouse", "lever", "ashby", "workable"}


# -- Lever ------------------------------------------------------------------


def test_lever_parses_postings():
    payload = [
        {
            "id": "abc-123",
            "text": "Backend Engineer",
            "categories": {"location": "Kathmandu, Nepal"},
            "hostedUrl": "https://jobs.lever.co/acme/abc-123",
            "applyUrl": "https://jobs.lever.co/acme/abc-123/apply",
            "createdAt": 1788199939703,
            "descriptionPlain": "do things",
        }
    ]
    postings = LeverAdapter(client=FakeClient(FakeResponse(200, payload))).fetch("acme")
    assert len(postings) == 1
    posting = postings[0]
    assert posting.posting_id == "abc-123"
    assert posting.title == "Backend Engineer"
    assert posting.location == "Kathmandu, Nepal"
    assert posting.canonical_url == "https://jobs.lever.co/acme/abc-123"
    assert posting.apply_target == "https://jobs.lever.co/acme/abc-123/apply"
    assert posting.posted_at == datetime.fromtimestamp(1788199939703 / 1000, tz=UTC)
    assert posting.description == "do things"


def test_lever_404_is_dead():
    client = FakeClient(FakeResponse(404, None))
    with pytest.raises(BoardError) as exc:
        LeverAdapter(client=client).fetch("missing")
    assert exc.value.dead is True


def test_lever_transport_error_is_not_dead():
    client = FakeClient(raises=httpx.ConnectError("boom"))
    with pytest.raises(BoardError) as exc:
        LeverAdapter(client=client).fetch("acme")
    assert exc.value.dead is False


# -- Ashby ------------------------------------------------------------------


def test_ashby_parses_and_skips_unlisted():
    payload = {
        "jobs": [
            {
                "id": "8fb1615c",
                "title": "Technical Program Manager",
                "location": "San Francisco",
                "jobUrl": "https://jobs.ashbyhq.com/openai/8fb1615c",
                "applyUrl": "https://jobs.ashbyhq.com/openai/8fb1615c/application",
                "publishedAt": "2026-03-12T16:38:15.322+00:00",
                "isListed": True,
                "descriptionHtml": "<p>hi</p>",
            },
            {"id": "draft-1", "title": "Hidden", "isListed": False},
        ]
    }
    postings = AshbyAdapter(client=FakeClient(FakeResponse(200, payload))).fetch("openai")
    assert [p.posting_id for p in postings] == ["8fb1615c"]
    posting = postings[0]
    assert posting.title == "Technical Program Manager"
    assert posting.location == "San Francisco"
    assert posting.canonical_url == "https://jobs.ashbyhq.com/openai/8fb1615c"
    assert posting.apply_target == "https://jobs.ashbyhq.com/openai/8fb1615c/application"
    assert posting.posted_at == datetime(2026, 3, 12, 16, 38, 15, 322000, tzinfo=UTC)


# -- Workable ---------------------------------------------------------------


def _workable_payload() -> dict:
    return {
        "name": "Acme",
        "description": "",
        "jobs": [
            {
                "shortcode": "BC6101898F",
                "title": "Account Manager",
                "country": "United Kingdom",
                "city": "London",
                "state": "England",
                "url": "https://apply.workable.com/j/BC6101898F",
                "application_url": "https://apply.workable.com/j/BC6101898F/apply",
                "published_on": "2026-06-16",
                "created_at": "2026-06-03",
                "locations": [
                    {
                        "country": "United Kingdom",
                        "region": "England",
                        "city": "London",
                        "hidden": False,
                    },
                    {"country": "Nepal", "region": "Bagmati", "city": "Kathmandu", "hidden": False},
                    {"country": "Nowhere", "city": "Hidden", "hidden": True},
                ],
                "description": "<p>role</p>",
            }
        ],
    }


def test_workable_parses_location_from_array_and_date():
    postings = WorkableAdapter(client=FakeClient(FakeResponse(200, _workable_payload()))).fetch(
        "acme"
    )
    assert len(postings) == 1
    posting = postings[0]
    assert posting.posting_id == "BC6101898F"
    assert posting.title == "Account Manager"
    assert posting.location == (
        "London, England, United Kingdom | Kathmandu, Bagmati, Nepal"
    )  # hidden location dropped
    assert posting.canonical_url == "https://apply.workable.com/j/BC6101898F"
    assert posting.apply_target == "https://apply.workable.com/j/BC6101898F/apply"
    assert posting.posted_at == datetime(2026, 6, 16, tzinfo=UTC)
    assert posting.description == "<p>role</p>"


def test_workable_falls_back_to_top_level_location():
    payload = _workable_payload()
    payload["jobs"][0]["locations"] = []
    posting = WorkableAdapter(client=FakeClient(FakeResponse(200, payload))).fetch("acme")[0]
    assert posting.location == "London, England, United Kingdom"


def test_workable_404_is_dead():
    client = FakeClient(FakeResponse(404, {"message": "Not Found"}))
    with pytest.raises(BoardError) as exc:
        WorkableAdapter(client=client).fetch("missing")
    assert exc.value.dead is True


# -- Greenhouse (locks the shared fetch helper behavior) --------------------


def test_greenhouse_still_parses_postings():
    payload = {
        "jobs": [
            {
                "id": 900,
                "title": "Platform Engineer",
                "location": {"name": "Kathmandu"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/900",
                "first_published": "2026-03-12T16:38:15-04:00",
                "content": "<p>role</p>",
            }
        ]
    }
    postings = GreenhouseAdapter(client=FakeClient(FakeResponse(200, payload))).fetch("acme")
    assert len(postings) == 1
    assert postings[0].posting_id == "900"
    assert postings[0].location == "Kathmandu"
    assert postings[0].posted_at == datetime(2026, 3, 12, 20, 38, 15, tzinfo=UTC)
