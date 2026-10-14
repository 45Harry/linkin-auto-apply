"""The hourly cycle and its steps.

Each step is isolated: one failing step never stops the next. Every source level
result feeds `health.record_run`, which decides when to send a failure or
recovery alert (spec 0001, AC-15, AC-17).
"""

from __future__ import annotations

import logging
import sqlite3

from . import alerts, criteria, filter, health, parse
from .config import Settings
from .db import transaction
from .dedupe import ats_dedupe_key
from .repo import companies, jobs, source_health
from .sources.ashby import AshbyAdapter
from .sources.base import BoardAdapter, BoardError
from .sources.gmail_alerts import run_gmail_alerts
from .sources.gmail_notifications import run_gmail_notifications
from .sources.greenhouse import GreenhouseAdapter
from .sources.lever import LeverAdapter
from .sources.workable import WorkableAdapter
from .steps import StepResult
from .timeutil import now_iso

log = logging.getLogger("jobbot.cycle")

BOARD_DEATH_THRESHOLD = 3


def _adapters() -> dict[str, BoardAdapter]:
    return {
        "greenhouse": GreenhouseAdapter(),
        "lever": LeverAdapter(),
        "ashby": AshbyAdapter(),
        "workable": WorkableAdapter(),
    }


def _board_key(ats_type: str, ats_token: str) -> str:
    return f"ats_board:{ats_type}:{ats_token}"


def run_ats_boards(conn: sqlite3.Connection, settings: Settings) -> StepResult:
    adapters = _adapters()
    boards = companies.boards_to_poll(conn)
    total = 0
    failed = 0
    created = 0
    expired = 0
    seen_at = now_iso()

    for company in boards:
        adapter = adapters.get(company["ats_type"])
        if adapter is None:
            continue
        total += 1
        key = _board_key(company["ats_type"], company["ats_token"])
        try:
            postings = adapter.fetch(company["ats_token"])
        except BoardError as exc:
            failed += 1
            _record_board_failure(conn, company, key, seen_at, str(exc), exc.dead)
            log.warning(
                "board fetch failed",
                extra={"company_id": company["id"], "error": str(exc), "dead": exc.dead},
            )
            continue

        source_health.upsert(
            conn,
            key,
            status="ok",
            consecutive_failures=0,
            last_success_at=seen_at,
        )
        seen_keys: set[str] = set()
        with transaction(conn):
            for posting in postings:
                _, was_created = jobs.upsert_ats_posting(
                    conn,
                    posting,
                    company,
                    seen_at=seen_at,
                    max_age_days=settings.max_job_age_days,
                )
                created += int(was_created)
                seen_keys.add(
                    ats_dedupe_key(posting.ats_type, posting.ats_token, posting.posting_id)
                )
            expired += jobs.sweep_missed_polls(
                conn, company_id=int(company["id"]), seen_keys=seen_keys
            )

    ok = (2 * failed) <= total
    error = f"{failed}/{total} boards failed" if failed else None
    return StepResult(
        ok=ok,
        error=error,
        summary={"boards": total, "failed": failed, "created": created, "expired": expired},
    )


def _record_board_failure(
    conn: sqlite3.Connection,
    company: sqlite3.Row,
    key: str,
    now: str,
    error: str,
    dead: bool,
) -> None:
    row = source_health.get(conn, key)
    failures = (int(row["consecutive_failures"]) if row else 0) + 1
    status = "failing" if dead and failures >= BOARD_DEATH_THRESHOLD else "ok"
    source_health.upsert(
        conn,
        key,
        status=status,
        consecutive_failures=failures,
        last_error_at=now,
        last_error=error,
    )
    if dead and failures >= BOARD_DEATH_THRESHOLD and company["ats_type"] != "none":
        companies.set_ats_type(conn, int(company["id"]), "none")
        log.warning(
            "board marked dead, company set to no board",
            extra={"company_id": company["id"], "failures": failures},
        )


def run_expire_and_filter(conn: sqlite3.Connection, settings: Settings) -> StepResult:
    loaded = criteria.load(settings.data_dir)
    with transaction(conn):
        summary = filter.light_filter(
            conn,
            now_iso=now_iso(),
            max_age_days=settings.max_job_age_days,
            exclude_keywords=loaded.exclude_keywords,
        )
    return StepResult(ok=True, summary=summary)


def hourly_cycle(conn: sqlite3.Connection, settings: Settings) -> dict[str, object]:
    summaries: dict[str, object] = {}
    # (health source key or None, step). Steps run in the fixed spec order.
    steps: list[tuple[str | None, object]] = [
        ("gmail_alert", run_gmail_alerts),
        ("gmail_notification", run_gmail_notifications),
        ("ats", run_ats_boards),
        (None, parse.run_parse_pending),
        (None, run_expire_and_filter),
    ]

    for source, step in steps:
        label = source or getattr(step, "__name__", "step")
        try:
            result: StepResult = step(conn, settings)  # type: ignore[operator]
        except Exception as exc:  # noqa: BLE001 - a step must never stop the cycle
            log.exception("cycle step crashed", extra={"source": label})
            result = StepResult(ok=False, error=str(exc))

        if source is not None:
            event = health.record_run(conn, source, ok=result.ok, now=now_iso(), error=result.error)
            _alert_on_event(settings, source, event, result.error)
        summaries[label] = result.summary
        log.info(
            "cycle step done",
            extra={"source": label, "ok": result.ok, "summary": result.summary},
        )

    log.info("hourly cycle done", extra={"summaries": summaries})
    return summaries


def _alert_on_event(
    settings: Settings, source: str, event: health.HealthEvent, error: str | None
) -> None:
    if event is health.HealthEvent.FAILING:
        subject = f"[jobbot] source failing: {source}"
        body = f"The {source} source has failed 3 runs in a row.\nLast error: {error}\n"
        alerts.send_alert(settings, subject=subject, body=body)
    elif event is health.HealthEvent.RECOVERED:
        subject = f"[jobbot] source recovered: {source}"
        body = f"The {source} source is succeeding again.\n"
        alerts.send_alert(settings, subject=subject, body=body)
