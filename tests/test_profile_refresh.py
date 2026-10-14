"""Tests for the profile refresh slice (spec 0001, AC-11, AC-12).

PDF reading and GitHub are fakes, so nothing touches the network or the disk PDFs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jobbot import profile as prof
from jobbot.ai.router import AiRouter
from jobbot.config import Settings
from jobbot.db import connect
from jobbot.migrate import migrate

T0 = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
CRITERIA = {
    "titles": ["AI Engineer", "ML Engineer"],
    "keywords": ["voice"],
    "locations": ["Kathmandu", "Remote"],
    "seniority": ["senior"],
    "exclude_keywords": ["sales"],
}


class FakeGitHub:
    def __init__(self, snapshot: dict) -> None:
        self._snapshot = snapshot
        self.calls = 0

    def snapshot(self, username: str) -> dict:
        self.calls += 1
        return dict(self._snapshot)


class FakeProvider:
    def __init__(self, reply: str | None = None) -> None:
        self.name = "claude"
        self.hosted = True
        self._reply = reply

    def complete(self, *, system: str, user: str) -> str:
        if self._reply is None:
            raise RuntimeError("down")
        return self._reply


def settings_for(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        _env_file=None,
        data_dir=tmp_path,
        tz="Asia/Kathmandu",
        github_username="45Harry",
        anthropic_api_key="x",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def conn(tmp_path):
    settings = settings_for(tmp_path)
    connection = connect(settings.db_path)
    migrate(connection)
    yield connection
    connection.close()


def write_profile(tmp_path: Path, *, cv: str | None = "CV TEXT", linkedin: str | None = None):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    if cv is not None:
        (profile_dir / "cv.pdf").write_text(cv)
    if linkedin is not None:
        (profile_dir / "linkedin.pdf").write_text(linkedin)


def reader(*, cv: str = "CV TEXT", linkedin: str = ""):
    def _read(path: Path) -> str:
        if path.name == "cv.pdf":
            return cv
        if path.name == "linkedin.pdf":
            return linkedin
        return ""

    return _read


def router_with(settings, conn, reply):
    return AiRouter(settings, conn, providers=[FakeProvider(reply)], alert_sink=lambda *a: None)


def test_generates_criteria_and_sends_email_once(conn, tmp_path):
    settings = settings_for(tmp_path)
    write_profile(tmp_path)
    alerts: list[tuple[str, str]] = []
    router = router_with(settings, conn, json.dumps(CRITERIA))

    result = prof.run_profile_refresh(
        conn,
        settings,
        now=T0,
        router=router,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(),
        alert_sink=lambda s, b: alerts.append((s, b)),
    )
    assert result.ok and result.summary["regenerated"] is True
    assert result.summary["email"] is True
    assert len(alerts) == 1

    payload = json.loads((tmp_path / "criteria.json").read_text())
    assert payload["titles"] == ["AI Engineer", "ML Engineer"]
    assert payload["generated_by"] == "claude"
    assert payload["alerts_email_sent_for"] == payload["alert_set_hash"]
    assert set(payload) == {
        "titles",
        "keywords",
        "locations",
        "seniority",
        "exclude_keywords",
        "sources_hash",
        "alert_set_hash",
        "alerts_email_sent_for",
        "generated_at",
        "generated_by",
    }


def test_stable_rerun_sends_no_email(conn, tmp_path):
    settings = settings_for(tmp_path)
    write_profile(tmp_path)
    alerts: list[tuple[str, str]] = []
    router = router_with(settings, conn, json.dumps(CRITERIA))
    sink = lambda s, b: alerts.append((s, b))  # noqa: E731

    prof.run_profile_refresh(
        conn,
        settings,
        now=T0,
        router=router,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(),
        alert_sink=sink,
    )
    result = prof.run_profile_refresh(
        conn,
        settings,
        now=T0 + timedelta(hours=1),
        router=router,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(),
        alert_sink=sink,
    )
    assert result.summary["regenerated"] is False
    assert len(alerts) == 1  # only the first run


def test_pdf_change_regenerates_without_email_when_set_same(conn, tmp_path):
    settings = settings_for(tmp_path)
    write_profile(tmp_path, cv="OLD")
    alerts: list[tuple[str, str]] = []
    router = router_with(settings, conn, json.dumps(CRITERIA))
    sink = lambda s, b: alerts.append((s, b))  # noqa: E731

    prof.run_profile_refresh(
        conn,
        settings,
        now=T0,
        router=router,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(cv="OLD"),
        alert_sink=sink,
    )
    result = prof.run_profile_refresh(
        conn,
        settings,
        now=T0 + timedelta(minutes=5),
        router=router,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(cv="NEW"),
        alert_sink=sink,
    )
    assert result.summary["regenerated"] is True
    assert result.summary["email"] is False  # same titles and locations, AC-12
    assert len(alerts) == 1


def test_github_change_regenerates_on_weekly_refresh(conn, tmp_path):
    settings = settings_for(tmp_path)
    write_profile(tmp_path)
    alerts: list[tuple[str, str]] = []
    router = router_with(settings, conn, json.dumps(CRITERIA))
    sink = lambda s, b: alerts.append((s, b))  # noqa: E731

    prof.run_profile_refresh(
        conn,
        settings,
        now=T0,
        router=router,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(),
        alert_sink=sink,
    )
    result = prof.run_profile_refresh(
        conn,
        settings,
        now=T0 + timedelta(days=8),
        router=router,
        github=FakeGitHub({"bio": "b"}),
        read_pdf=reader(),
        alert_sink=sink,
    )
    assert result.summary["regenerated"] is True
    assert result.summary["email"] is False


def test_github_not_fetched_before_week(conn, tmp_path):
    settings = settings_for(tmp_path)
    write_profile(tmp_path)
    router = router_with(settings, conn, json.dumps(CRITERIA))
    gh1 = FakeGitHub({"bio": "a"})
    prof.run_profile_refresh(
        conn,
        settings,
        now=T0,
        router=router,
        github=gh1,
        read_pdf=reader(),
        alert_sink=lambda *a: None,
    )
    gh2 = FakeGitHub({"bio": "a"})
    prof.run_profile_refresh(
        conn,
        settings,
        now=T0 + timedelta(hours=1),
        router=router,
        github=gh2,
        read_pdf=reader(),
        alert_sink=lambda *a: None,
    )
    assert gh1.calls == 1 and gh2.calls == 0


def test_missing_cv_writes_empty_criteria_and_alerts_once(conn, tmp_path):
    settings = settings_for(tmp_path, github_username=None)
    write_profile(tmp_path, cv=None)
    alerts: list[tuple[str, str]] = []
    sink = lambda s, b: alerts.append((s, b))  # noqa: E731

    first = prof.run_profile_refresh(
        conn, settings, now=T0, read_pdf=reader(cv=""), alert_sink=sink
    )
    assert first.ok
    assert first.summary["role_queries_skipped"] is True
    assert any("no CV" in subject for subject, _ in alerts)
    payload = json.loads((tmp_path / "criteria.json").read_text())
    assert payload["titles"] == [] and payload["locations"] == []

    before = len(alerts)
    prof.run_profile_refresh(
        conn, settings, now=T0 + timedelta(hours=1), read_pdf=reader(cv=""), alert_sink=sink
    )
    assert len(alerts) == before  # no repeat


def test_generation_failure_keeps_old_and_retries(conn, tmp_path):
    settings = settings_for(tmp_path)
    write_profile(tmp_path)
    good = router_with(settings, conn, json.dumps(CRITERIA))
    prof.run_profile_refresh(
        conn,
        settings,
        now=T0,
        router=good,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(),
        alert_sink=lambda *a: None,
    )

    write_profile(tmp_path, cv="CHANGED")
    bad = AiRouter(settings, conn, providers=[FakeProvider(None)], alert_sink=lambda *a: None)
    result = prof.run_profile_refresh(
        conn,
        settings,
        now=T0 + timedelta(minutes=5),
        router=bad,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(cv="CHANGED"),
        alert_sink=lambda *a: None,
    )
    assert result.ok is False
    assert json.loads((tmp_path / "criteria.json").read_text())["titles"] == CRITERIA["titles"]

    # unchanged failure means the next run retries (cv hash was not committed)
    again = prof.run_profile_refresh(
        conn,
        settings,
        now=T0 + timedelta(minutes=6),
        router=bad,
        github=FakeGitHub({"bio": "a"}),
        read_pdf=reader(cv="CHANGED"),
        alert_sink=lambda *a: None,
    )
    assert again.ok is False


def test_search_pairs_cap_and_link():
    payload = {"titles": ["A", "B", "C"], "locations": ["X", "Y", "Z", "W"]}
    pairs = prof._search_pairs(payload)
    assert len(pairs) == 10
    many = {"titles": [f"T{i}" for i in range(20)], "locations": ["Kathmandu"]}
    assert len(prof._search_pairs(many)) == 10
    link = prof._search_link("AI Engineer", "Kathmandu")
    assert link.startswith("https://www.linkedin.com/jobs/search/?")
    assert (
        "keywords=AI+Engineer" in link and "location=Kathmandu" in link and "f_TPR=r86400" in link
    )
