"""The AI router: provider order, schema validated fallback, the hosted daily cap,
and the "all providers down" alert (spec 0001, AC-10).

- Order: Ollama, Claude, Grok, Gemini. A provider is skipped on error, timeout, or
  output that fails schema validation.
- If every provider fails, `parse` returns `(None, None)` and the caller leaves the
  raw item `pending`; it is retried each run until it ages past 14 days.
- Hosted calls (Claude, Grok, Gemini) share `AI_HOSTED_DAILY_CAP` per day in `TZ`.
  When the cap is hit, hosted providers are skipped and one alert is sent that day.
- When every provider has failed for more than 6 hours (from the last success, or
  from container start when there was never one), one alert is sent.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TypeVar

from pydantic import BaseModel

from ..config import Settings
from ..repo import source_health
from ..timeutil import local_date_of, local_today, now_utc, parse_iso, to_iso
from .providers import Provider, build_providers, extract_json
from .schemas import SCHEMA_HINTS

log = logging.getLogger("jobbot.ai.router")

HOSTED_AI_SOURCE = "ai_hosted"
AI_CHAIN_SOURCE = "ai_chain"
CHAIN_ALERT_AFTER = timedelta(hours=6)
CONTAINER_START = now_utc()

SYSTEM_PROMPT = (
    "You extract structured job information from text. Fill a field only when the "
    "source states it; never guess. Reply with JSON only."
)

ModelT = TypeVar("ModelT", bound=BaseModel)

AlertSink = Callable[[str, str], None]


def _default_alert_sink(settings: Settings) -> AlertSink:
    from .. import alerts

    def _sink(subject: str, body: str) -> None:
        alerts.send_alert(settings, subject=subject, body=body)

    return _sink


class AiRouter:
    def __init__(
        self,
        settings: Settings,
        conn: sqlite3.Connection,
        *,
        providers: list[Provider] | None = None,
        alert_sink: AlertSink | None = None,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self._settings = settings
        self._conn = conn
        self._providers = providers if providers is not None else build_providers(settings)
        self._alert = alert_sink or _default_alert_sink(settings)
        self._clock = clock

    def parse(
        self, *, user: str, model_cls: type[ModelT], system: str | None = None
    ) -> tuple[ModelT | None, str | None]:
        """Parse an item. Returns `(model, provider_name)`, or `(None, None)` if all fail."""
        base = system if system is not None else SYSTEM_PROMPT
        system_prompt = f"{base}\n{SCHEMA_HINTS.get(model_cls, '')}".strip()
        last_error: str | None = None
        cap_blocked = False

        for provider in self._providers:
            if provider.hosted:
                if self._hosted_cap_reached():
                    cap_blocked = True
                    continue
                self._consume_hosted()
            try:
                text = provider.complete(system=system_prompt, user=user)
                data = extract_json(text)
                model = model_cls.model_validate(data)
            except Exception as exc:  # noqa: BLE001 - any provider problem means skip it
                last_error = f"{provider.name}: {exc}"
                log.warning("provider failed", extra={"provider": provider.name})
                continue
            self._record_chain(ok=True)
            return model, provider.name

        self._record_chain(ok=False, error=last_error)
        if cap_blocked and self._hosted_cap_reached():
            self._maybe_alert_cap()
        self._maybe_alert_chain()
        return None, None

    # -- hosted cap ---------------------------------------------------------

    def _hosted_used_today(self) -> int:
        today = local_today(self._settings.tz)
        row = source_health.get(self._conn, HOSTED_AI_SOURCE)
        if row is None or row["quota_period"] != today:
            source_health.upsert(self._conn, HOSTED_AI_SOURCE, quota_used=0, quota_period=today)
            return 0
        return int(row["quota_used"] or 0)

    def _hosted_cap_reached(self) -> bool:
        return self._hosted_used_today() >= self._settings.ai_hosted_daily_cap

    def _consume_hosted(self) -> None:
        today = local_today(self._settings.tz)
        used = self._hosted_used_today()
        source_health.upsert(self._conn, HOSTED_AI_SOURCE, quota_used=used + 1, quota_period=today)

    def _maybe_alert_cap(self) -> None:
        today = local_today(self._settings.tz)
        row = source_health.get(self._conn, HOSTED_AI_SOURCE)
        if (
            row
            and row["alerted_at"]
            and local_date_of(row["alerted_at"], self._settings.tz) == today
        ):
            return
        self._alert(
            "[jobbot] hosted AI cap reached",
            f"Hosted AI calls hit the daily cap of {self._settings.ai_hosted_daily_cap}. "
            "Items wait as pending until the next day in "
            f"{self._settings.tz}.\n",
        )
        source_health.upsert(self._conn, HOSTED_AI_SOURCE, alerted_at=to_iso(self._clock()))

    # -- chain health -------------------------------------------------------

    def _record_chain(self, *, ok: bool, error: str | None = None) -> None:
        now = to_iso(self._clock())
        if ok:
            source_health.upsert(
                self._conn,
                AI_CHAIN_SOURCE,
                status="ok",
                last_success_at=now,
                consecutive_failures=0,
            )
            return
        row = source_health.get(self._conn, AI_CHAIN_SOURCE)
        failures = (int(row["consecutive_failures"]) if row else 0) + 1
        source_health.upsert(
            self._conn,
            AI_CHAIN_SOURCE,
            last_error_at=now,
            last_error=error,
            consecutive_failures=failures,
        )

    def _maybe_alert_chain(self) -> None:
        row = source_health.get(self._conn, AI_CHAIN_SOURCE)
        last_success = parse_iso(row["last_success_at"]) if row and row["last_success_at"] else None
        reference = last_success or CONTAINER_START
        now = self._clock()
        if now - reference <= CHAIN_ALERT_AFTER:
            return
        alerted_at = parse_iso(row["alerted_at"]) if row and row["alerted_at"] else None
        if alerted_at is not None and alerted_at >= reference:
            return
        self._alert(
            "[jobbot] AI parsing down",
            "Every AI provider has failed for more than 6 hours. Items wait as pending.\n",
        )
        source_health.upsert(self._conn, AI_CHAIN_SOURCE, status="failing", alerted_at=to_iso(now))
