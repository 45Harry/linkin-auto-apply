"""Turn email and page content into plain text, and pull out only what is published.

Used for rules based extraction and for enforcing AC-9: a contact email or phone is
kept only when it appears verbatim in the source text.
"""

from __future__ import annotations

import html as html_lib
import re

_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_LINE_SPACES = re.compile(r"[ \t]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+\d[\d\-\s().]{7,}\d|\b\d{3}[\-\s]\d{3}[\-\s]\d{4}\b)")

# Addresses that show up in email footers, never a real contact.
EMAIL_DENYLIST = {
    "noreply@linkedin.com",
    "no-reply@linkedin.com",
    "notifications-noreply@linkedin.com",
    "jobalerts-noreply@linkedin.com",
    "jobs-listings@linkedin.com",
    "messages-noreply@linkedin.com",
}


def strip_tags(markup: str) -> str:
    text = _SCRIPT.sub(" ", markup)
    text = _TAG.sub(" ", text)
    return html_lib.unescape(text)


def to_text(markup: str) -> str:
    """Best effort HTML to text, keeping line structure for line based rules."""
    without_scripts = _SCRIPT.sub(" ", markup)
    with_breaks = re.sub(
        r"<\s*(br|/p|/div|/li|/tr|/h[1-6])\s*/?>", "\n", without_scripts, flags=re.IGNORECASE
    )
    text = _TAG.sub(" ", with_breaks)
    text = html_lib.unescape(text)
    text = "\n".join(_LINE_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return _MANY_NEWLINES.sub("\n\n", text).strip()


def find_email(text: str) -> str | None:
    for match in EMAIL_RE.finditer(text):
        candidate = match.group(0)
        if candidate.lower() not in EMAIL_DENYLIST:
            return candidate
    return None


def find_phone(text: str) -> str | None:
    match = PHONE_RE.search(text)
    return match.group(0).strip() if match else None


def find_linkedin_profile(text: str) -> str | None:
    match = re.search(r"https?://[a-z.]*linkedin\.com/in/[A-Za-z0-9\-_%]+", text)
    return match.group(0) if match else None


def appears_in(value: str | None, text: str) -> bool:
    return bool(value) and value is not None and value in text
