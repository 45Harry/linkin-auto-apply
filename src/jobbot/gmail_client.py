"""Gmail access: OAuth setup, token loading, and sending. Least privilege scopes
only (`gmail.readonly` plus `gmail.send`)."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

log = logging.getLogger("jobbot.gmail")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

PAGE_SIZE = 100
MAX_MESSAGES = 2000


def load_credentials(token_file: Path) -> Credentials | None:
    if not token_file.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    except (ValueError, OSError) as exc:
        log.warning("gmail token unreadable", extra={"error": str(exc)})
        return None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _write_token(token_file, creds)
        except Exception as exc:  # noqa: BLE001 - token refresh can fail many ways
            log.warning("gmail token refresh failed", extra={"error": str(exc)})
            return None
    return creds if creds and creds.valid else None


def _write_token(token_file: Path, creds: Credentials) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    token_file.chmod(0o600)


def run_oauth_flow(client_file: Path, token_file: Path) -> Credentials:
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(port=0)
    _write_token(token_file, creds)
    return creds


def my_address(creds: Credentials) -> str | None:
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress")
    except Exception as exc:  # noqa: BLE001
        log.warning("gmail profile lookup failed", extra={"error": str(exc)})
        return None


def send_message(creds: Credentials, *, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


@dataclass
class GmailMessage:
    """One message, already decoded into the parts the sources need."""

    id: str
    internal_date: datetime
    sender: str
    subject: str
    snippet: str
    text: str
    html: str | None


class GmailReader(Protocol):
    def search(self, query: str, *, max_messages: int = MAX_MESSAGES) -> list[GmailMessage]: ...


class GmailReadError(Exception):
    """Reading Gmail failed (for example a revoked token)."""


class ApiGmailReader:
    """Reads messages through the Gmail API, paging through every result page."""

    def __init__(self, creds: Credentials) -> None:
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def search(self, query: str, *, max_messages: int = MAX_MESSAGES) -> list[GmailMessage]:
        ids: list[str] = []
        token: str | None = None
        try:
            while True:
                response = (
                    self._service.users()
                    .messages()
                    .list(
                        userId="me",
                        q=query,
                        pageToken=token,
                        maxResults=min(PAGE_SIZE, max_messages - len(ids)),
                    )
                    .execute()
                )
                ids.extend(message["id"] for message in response.get("messages", []))
                token = response.get("nextPageToken")
                if not token or len(ids) >= max_messages:
                    break
            return [self._get(message_id) for message_id in ids]
        except Exception as exc:  # noqa: BLE001 - many transport errors possible
            raise GmailReadError(str(exc)) from exc

    def _get(self, message_id: str) -> GmailMessage:
        payload = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        return _to_message(payload)


def _header(payload: dict, name: str) -> str:
    for header in payload.get("payload", {}).get("headers", []):
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _decode(data: str | None) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _collect_parts(payload: dict, out: dict[str, str]) -> None:
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")
    if mime == "text/plain" and body_data and "text" not in out:
        out["text"] = _decode(body_data)
    elif mime == "text/html" and body_data and "html" not in out:
        out["html"] = _decode(body_data)
    for part in payload.get("parts", []) or []:
        _collect_parts(part, out)


def _to_message(payload: dict) -> GmailMessage:
    parts: dict[str, str] = {}
    _collect_parts(payload.get("payload", {}), parts)
    internal_ms = int(payload.get("internalDate") or 0)
    internal = (
        datetime.fromtimestamp(internal_ms / 1000, tz=UTC) if internal_ms else datetime.now(UTC)
    )
    return GmailMessage(
        id=payload.get("id", ""),
        internal_date=internal,
        sender=_header(payload, "From"),
        subject=_header(payload, "Subject"),
        snippet=payload.get("snippet", ""),
        text=parts.get("text", ""),
        html=parts.get("html"),
    )
