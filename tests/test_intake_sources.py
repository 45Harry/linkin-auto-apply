"""Tests for the AI parsing and Gmail sources slice (spec 0001).

Covers AC-1, AC-2, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10 with fakes for Gmail and
the AI providers, so nothing touches the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from jobbot import filter as filter_mod
from jobbot.ai.router import AiRouter
from jobbot.ai.schemas import ParsedPost
from jobbot.config import Settings
from jobbot.dates import activity_timestamp, choose_posted_at, parse_relative
from jobbot.db import connect
from jobbot.dedupe import ats_dedupe_key
from jobbot.gmail_client import GmailMessage
from jobbot.migrate import migrate
from jobbot.parse import run_parse_pending
from jobbot.repo import companies, jobs, raw_items, sightings
from jobbot.sources.base import AtsPosting
from jobbot.sources.gmail_alerts import run_gmail_alerts
from jobbot.sources.gmail_notifications import run_gmail_notifications
from jobbot.sources.linkedin_email import extract_alert_postings


class FakeReader:
    def __init__(self, messages: list[GmailMessage]) -> None:
        self._messages = messages
        self.queries: list[str] = []

    def search(self, query: str, *, max_messages: int = 2000) -> list[GmailMessage]:
        self.queries.append(query)
        return list(self._messages)


class FakeProvider:
    def __init__(self, name: str, *, hosted: bool = False, reply: str | None = None) -> None:
        self.name = name
        self.hosted = hosted
        self._reply = reply

    def complete(self, *, system: str, user: str) -> str:
        if self._reply is None:
            raise RuntimeError("boom")
        return self._reply


def make_settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        tz="UTC",
        linkedin_notification_sender="notifications-noreply@linkedin.com",
    )


@pytest.fixture
def conn(tmp_path):
    settings = make_settings(tmp_path)
    connection = connect(settings.db_path)
    migrate(connection)
    yield connection
    connection.close()


def message(
    mid: str, *, text: str = "", html: str | None = None, days_ago: int = 0, snippet: str = ""
) -> GmailMessage:
    return GmailMessage(
        id=mid,
        internal_date=datetime.now(UTC) - timedelta(days=days_ago),
        sender="jobalerts-noreply@linkedin.com",
        subject="Alert",
        snippet=snippet or text[:120],
        text=text,
        html=html,
    )


# -- rules extraction -------------------------------------------------------


def test_extract_alert_postings_reads_title_company_location():
    html = (
        '<a href="https://www.linkedin.com/comm/jobs/view/101/?trk=abc">Senior Backend Engineer</a>'
        "<div>Kathmandu, Bagmati, Nepal</div><div>Acme Pvt. Ltd.</div>"
        '<a href="https://www.linkedin.com/comm/jobs/view/102/?trk=abc">Data Scientist</a>'
        "<div>Remote</div><div>Beta Inc</div>"
    )
    postings = extract_alert_postings(html, "")
    assert postings is not None
    by_id = {posting.job_id: posting for posting in postings}
    assert by_id["101"].title == "Senior Backend Engineer"
    assert by_id["101"].company == "Acme Pvt. Ltd."
    assert by_id["101"].location == "Kathmandu, Bagmati, Nepal"
    assert by_id["102"].location == "Remote"


def test_extract_alert_postings_returns_none_when_fields_missing():
    html = '<a href="https://www.linkedin.com/comm/jobs/view/101/">Engineer</a>'
    assert extract_alert_postings(html, "") is None


def test_alert_rules_creates_one_job_and_sighting(conn, tmp_path):
    settings = make_settings(tmp_path)
    html = (
        '<a href="https://www.linkedin.com/comm/jobs/view/101/?trk=x">Backend Engineer</a>'
        "<div>Kathmandu, Nepal</div><div>Acme Pvt. Ltd.</div>"
    )
    reader = FakeReader([message("m1", html=html)])
    run_gmail_alerts(conn, settings, reader=reader)
    job = jobs.find_by_dedupe_key(conn, "li:101")
    assert job is not None
    assert job["status"] == "new"
    assert job["canonical_url"] == "https://www.linkedin.com/comm/jobs/view/101"
    sight = sightings.list_for_job(conn, int(job["id"]))
    assert sight[0]["source"] == "gmail_alert"
    assert sight[0]["source_ref"] == "li:101"
    raw = raw_items.get_by_external(conn, "gmail_alert", "m1")
    assert raw["parse_status"] == "parsed"
    assert raw["parsed_by"] == "rules"


# -- AI fallback ------------------------------------------------------------


def test_alert_ai_fallback_parses_pending(conn, tmp_path):
    settings = make_settings(tmp_path)
    html = '<a href="https://www.linkedin.com/comm/jobs/view/201/">Engineer</a>'
    run_gmail_alerts(conn, settings, reader=FakeReader([message("m2", html=html)]))
    raw = raw_items.get_by_external(conn, "gmail_alert", "m2")
    assert raw["parse_status"] == "pending"

    reply = json.dumps(
        {
            "jobs": [
                {
                    "title": "AI Backend Engineer",
                    "company": "Acme Pvt. Ltd.",
                    "location": "Kathmandu",
                    "url": "https://www.linkedin.com/jobs/view/201",
                    "work_mode": "remote",
                }
            ]
        }
    )
    router = AiRouter(
        settings, conn, providers=[FakeProvider("ollama", reply=reply)], alert_sink=lambda *a: None
    )
    run_parse_pending(conn, settings, router=router)

    job = jobs.find_by_dedupe_key(conn, "li:201")
    assert job is not None
    assert job["work_mode"] == "remote"
    assert raw_items.get_by_external(conn, "gmail_alert", "m2")["parsed_by"] == "ollama"


def test_notification_rules_marks_not_job(conn, tmp_path):
    settings = make_settings(tmp_path)
    reader = FakeReader(
        [message("n1", text="See who viewed your profile this week.", snippet="See who viewed")]
    )
    run_gmail_notifications(conn, settings, reader=reader)
    raw = raw_items.get_by_external(conn, "gmail_notification", "n1")
    assert raw["parse_status"] == "not_job"


def test_notification_hiring_creates_job_and_contact(conn, tmp_path):
    settings = make_settings(tmp_path)
    text = (
        "We are hiring a Platform Engineer. Reach out to jane@acme.com "
        "https://www.linkedin.com/posts/jane-doe_platform-engineer-activity-7123456789012345678-abcd"
    )
    run_gmail_notifications(conn, settings, reader=FakeReader([message("n2", text=text)]))

    reply = json.dumps(
        {
            "is_hiring_post": True,
            "title": "Platform Engineer",
            "company": "Acme Pvt. Ltd.",
            "author_name": "Jane Doe",
            "author_linkedin_url": "https://www.linkedin.com/in/jane-doe",
            "contact_email": "jane@acme.com",
        }
    )
    router = AiRouter(
        settings, conn, providers=[FakeProvider("ollama", reply=reply)], alert_sink=lambda *a: None
    )
    run_parse_pending(conn, settings, router=router)

    activity = "7123456789012345678"
    job = jobs.find_by_dedupe_key(conn, f"post:{activity}")
    assert job is not None
    # exact date from the activity id, not estimated
    assert job["posted_at_estimated"] == 0
    assert job["posted_at"].startswith(activity_timestamp(activity).isoformat()[:19])
    from jobbot.repo import contacts

    stored = contacts.list_for_job(conn, int(job["id"]))
    assert stored[0]["role"] == "post_author"
    assert stored[0]["email"] == "jane@acme.com"


def test_notification_contact_email_only_from_source(conn, tmp_path):
    settings = make_settings(tmp_path)
    text = "We are hiring a QA Engineer. Apply on our site."
    run_gmail_notifications(conn, settings, reader=FakeReader([message("n3", text=text)]))
    reply = json.dumps(
        {
            "is_hiring_post": True,
            "title": "QA Engineer",
            "author_name": "Sam Smith",
            "contact_email": "guessed@nowhere.com",
        }
    )
    router = AiRouter(
        settings, conn, providers=[FakeProvider("ollama", reply=reply)], alert_sink=lambda *a: None
    )
    run_parse_pending(conn, settings, router=router)
    from jobbot.repo import contacts

    job = conn.execute("SELECT id FROM jobs LIMIT 1").fetchone()
    assert job is not None
    stored = contacts.list_for_job(conn, int(job["id"]))
    assert stored[0]["email"] is None  # never guessed


# -- dates ------------------------------------------------------------------


def test_relative_date_parsing():
    assert parse_relative("3 days ago") == timedelta(days=3)
    assert parse_relative("1w") == timedelta(weeks=1)
    assert parse_relative("2h") == timedelta(hours=2)
    assert parse_relative("no date here") is None


def test_choose_posted_at_order():
    now = datetime(2026, 10, 14, tzinfo=UTC)
    exact, est = choose_posted_at(exact=now - timedelta(days=1), first_seen=now)
    assert est == 0
    rel, est2 = choose_posted_at(relative=timedelta(weeks=3), source_ts=now, first_seen=now)
    assert est2 == 1
    assert rel == now - timedelta(weeks=3)


def test_activity_timestamp_is_exact():
    ts = activity_timestamp("7123456789012345678")
    assert ts == datetime.fromtimestamp((7123456789012345678 >> 22) / 1000, tz=UTC)


# -- filter and expiry ------------------------------------------------------


def test_filter_expires_and_promotes(conn, tmp_path):
    seen = datetime.now(UTC)
    old = seen - timedelta(days=20)
    jobs.upsert_parsed_job(
        conn,
        source="gmail_alert",
        source_ref="li:1",
        dedupe_key="li:1",
        title="Old Job",
        canonical_url=None,
        company_id=None,
        company_name="Acme Pvt. Ltd.",
        location="Kathmandu",
        work_mode=None,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        seniority=None,
        apply_method=None,
        apply_target=None,
        description=None,
        posted_at=old.isoformat(),
        posted_at_estimated=1,
        seen_at=seen.isoformat(),
    )
    jobs.upsert_parsed_job(
        conn,
        source="gmail_alert",
        source_ref="li:2",
        dedupe_key="li:2",
        title="Fresh Job",
        canonical_url=None,
        company_id=None,
        company_name="Acme Pvt. Ltd.",
        location="Kathmandu",
        work_mode=None,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        seniority=None,
        apply_method=None,
        apply_target=None,
        description=None,
        posted_at=seen.isoformat(),
        posted_at_estimated=0,
        seen_at=seen.isoformat(),
    )
    summary = filter_mod.light_filter(
        conn, now_iso=seen.isoformat(), max_age_days=14, exclude_keywords=[]
    )
    assert summary["expired"] == 1
    assert summary["ready"] == 1
    assert jobs.find_by_dedupe_key(conn, "li:1")["status"] == "expired"
    assert jobs.find_by_dedupe_key(conn, "li:2")["status"] == "ready"


def test_exclude_keyword_matches_whole_words_only():
    assert filter_mod.match_exclude_keyword("Marketing Intern", "Acme", ["intern"]) == "intern"
    assert filter_mod.match_exclude_keyword("Internal Tools Engineer", "Acme", ["intern"]) is None


# -- dedupe and merge -------------------------------------------------------


def test_alert_merges_with_board_by_match_hash(conn, tmp_path):
    settings = make_settings(tmp_path)
    company_id = companies.add(conn, name="Acme Pvt. Ltd.", ats_type="greenhouse", ats_token="acme")
    company = companies.get(conn, company_id)
    posting = AtsPosting(
        ats_type="greenhouse",
        ats_token="acme",
        posting_id="900",
        title="Senior Backend Engineer",
        location="Kathmandu",
        canonical_url="https://boards.greenhouse.io/acme/jobs/900",
    )
    _, created = jobs.upsert_ats_posting(
        conn, posting, company, seen_at=datetime.now(UTC).isoformat(), max_age_days=14
    )
    assert created

    html = (
        '<a href="https://www.linkedin.com/comm/jobs/view/500/?trk=y">Senior Backend Engineer</a>'
        "<div>Kathmandu, Bagmati, Nepal</div><div>Acme Pvt. Ltd.</div>"
    )
    run_gmail_alerts(conn, settings, reader=FakeReader([message("m9", html=html)]))

    count = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
    assert count == 1  # merged, board wins
    merged = jobs.find_by_dedupe_key(conn, ats_dedupe_key("greenhouse", "acme", "900"))
    assert merged["canonical_url"] == "https://boards.greenhouse.io/acme/jobs/900"
    assert len(sightings.list_for_job(conn, int(merged["id"]))) == 2


# -- AI router cap and chain ------------------------------------------------


def test_ai_all_fail_stays_pending(conn, tmp_path):
    settings = make_settings(tmp_path)
    router = AiRouter(
        settings, conn, providers=[FakeProvider("ollama")], alert_sink=lambda *a: None
    )
    model, provider = router.parse(user="x", model_cls=ParsedPost)
    assert model is None and provider is None
    row = conn.execute("SELECT * FROM source_health WHERE source='ai_chain'").fetchone()
    assert int(row["consecutive_failures"]) == 1


def test_ai_hosted_cap_blocks_and_alerts(conn, tmp_path):
    settings = make_settings(tmp_path)
    settings.ai_hosted_daily_cap = 1
    alerts: list[tuple[str, str]] = []
    router = AiRouter(
        settings,
        conn,
        providers=[
            FakeProvider("claude", hosted=True),
            FakeProvider("grok", hosted=True, reply="{}"),
        ],
        alert_sink=lambda s, b: alerts.append((s, b)),
    )
    router.parse(user="x", model_cls=ParsedPost)
    row = conn.execute("SELECT * FROM source_health WHERE source='ai_hosted'").fetchone()
    assert int(row["quota_used"]) == 1
    assert alerts and "cap" in alerts[0][0]


def test_ai_chain_alert_after_six_hours(conn, tmp_path):
    settings = make_settings(tmp_path)
    alerts: list[tuple[str, str]] = []
    future = datetime.now(UTC) + timedelta(hours=7)
    router = AiRouter(
        settings,
        conn,
        providers=[FakeProvider("ollama")],
        alert_sink=lambda s, b: alerts.append((s, b)),
        clock=lambda: future,
    )
    router.parse(user="x", model_cls=ParsedPost)
    assert any("AI parsing down" in subject for subject, _ in alerts)
