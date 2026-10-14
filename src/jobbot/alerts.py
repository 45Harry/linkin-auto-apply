"""Alert delivery: Gmail first, then an ntfy push topic when Gmail sending fails
(spec 0001, AC-15)."""

from __future__ import annotations

import logging

import httpx

from . import gmail_client
from .config import Settings

log = logging.getLogger("jobbot.alerts")


def send_alert(settings: Settings, *, subject: str, body: str) -> str:
    """Send an alert. Returns the channel used: `gmail`, `ntfy`, or `none`."""
    creds = gmail_client.load_credentials(settings.resolved_gmail_token_file)
    if creds is not None:
        try:
            recipient = settings.alert_email_to or gmail_client.my_address(creds)
            if recipient:
                gmail_client.send_message(creds, to=recipient, subject=subject, body=body)
                return "gmail"
            log.warning("no alert recipient and no gmail address")
        except Exception as exc:  # noqa: BLE001 - fall back to ntfy
            log.warning("gmail alert send failed", extra={"error": str(exc)})

    if settings.ntfy_topic:
        _send_ntfy(settings, subject, body)
        return "ntfy"

    log.error("no alert channel available", extra={"subject": subject})
    return "none"


def _send_ntfy(settings: Settings, subject: str, body: str) -> None:
    url = f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}"
    try:
        httpx.post(
            url,
            content=body.encode("utf-8"),
            headers={"Title": subject, "Priority": "high"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        log.error("ntfy alert failed", extra={"error": str(exc)})
