"""Rules based extraction for LinkedIn job alert and notification emails.

The alert HTML is a template that changes over time, so rules are conservative:
they claim an email only when they can read a title, a company, and a location for
every listed posting. Anything less falls back to the AI parser (spec 0001, AC-1,
AC-2, AC-8). Job ids always come from `/jobs/view/(\\d+)`, so tracking parameters
never change the sighting key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..text_extract import strip_tags, to_text

JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")
JOB_URL_RE = re.compile(r"https?://[^\s\"'<>]*?/jobs/view/(\d+)", re.IGNORECASE)
_ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=\"([^\"]*?/jobs/view/(\d+)[^\"]*)\"[^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_COMPANY_LINK_RE = re.compile(r"linkedin\.com/company/([A-Za-z0-9%._\-]+)", re.IGNORECASE)

_REMOTE_WORDS = {"remote", "on-site", "onsite", "hybrid", "hybrid remote", "worldwide"}

HIRING_HINTS = (
    "hiring",
    "we're hiring",
    "we are hiring",
    "now hiring",
    "looking for",
    "join our team",
    "open role",
    "open position",
    "vacancy",
    "job opening",
    "we have an opening",
    "dm me",
)


@dataclass
class AlertPosting:
    job_id: str
    title: str
    url: str
    company: str | None
    location: str | None


def canonical_job_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}"


def _pretty_slug(slug: str) -> str:
    cleaned = re.sub(r"[-_]+", " ", slug)
    cleaned = re.sub(r"%[0-9A-Fa-f]{2}", " ", cleaned)
    return " ".join(word.capitalize() for word in cleaned.split()).strip()


def _block_lines(block: str) -> list[str]:
    text = to_text(block) if "<" in block else block
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_noise(line: str) -> bool:
    low = line.lower()
    return (
        line in {"View job", "View", "Apply", "Apply now"}
        or low.startswith("view job")
        or "jobs/view/" in line
        or line.startswith("http")
    )


def _looks_like_location(line: str) -> bool:
    low = line.lower()
    if low in _REMOTE_WORDS:
        return True
    return "," in line and not any(char.isdigit() for char in line)


def _company_location(lines: list[str]) -> tuple[str | None, str | None]:
    company: str | None = None
    location: str | None = None
    for line in lines:
        if _is_noise(line):
            continue
        if location is None and _looks_like_location(line):
            location = line
        elif company is None:
            company = line
    return company, location


def extract_alert_postings(html: str | None, text: str) -> list[AlertPosting] | None:
    """Return the postings when the email is confidently parsed, else `None`.

    `None` means the caller should fall back to the AI parser for the whole email.
    """
    postings: dict[str, AlertPosting] = {}

    source = html or ""
    if source:
        anchors = list(_ANCHOR_RE.finditer(source))
        for index, match in enumerate(anchors):
            url, job_id, anchor_html = match.group(1), match.group(2), match.group(3)
            if job_id in postings:
                continue
            title = strip_tags(anchor_html).strip()
            if not title:
                continue
            end = anchors[index + 1].start() if index + 1 < len(anchors) else len(source)
            company, location = _company_location(_block_lines(source[match.end() : end]))
            if company is None:
                found = _COMPANY_LINK_RE.search(source[match.start() : end])
                if found:
                    company = _pretty_slug(found.group(1))
            postings[job_id] = AlertPosting(
                job_id=job_id,
                title=title,
                url=url or canonical_job_url(job_id),
                company=company,
                location=location,
            )

    if not postings:
        for job_id, (title, company, location) in _split_text_on_jobs(text).items():
            postings[job_id] = AlertPosting(
                job_id=job_id,
                title=title,
                url=canonical_job_url(job_id),
                company=company,
                location=location,
            )

    if not postings:
        return None
    if not all(p.title and p.company and p.location for p in postings.values()):
        return None
    return list(postings.values())


def _split_text_on_jobs(text: str) -> dict[str, tuple[str, str | None, str | None]]:
    """Plain text fallback: lines before each job URL are location, company, title."""
    found: dict[str, tuple[str, str | None, str | None]] = {}
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        match = JOB_URL_RE.search(line) or JOB_ID_RE.search(line)
        if not match:
            continue
        job_id = match.group(1)
        preceding = [
            item for item in lines[max(0, index - 4) : index] if item and not _is_noise(item)
        ]
        title = preceding[-1] if preceding else ""
        company, location = _company_location(preceding[:-1])
        if job_id not in found:
            found[job_id] = (title, company, location)
    return found


def looks_like_hiring_post(snippet: str, text: str, url: str | None = None) -> bool:
    haystack = f"{snippet}\n{text}\n{url or ''}".lower()
    return any(hint in haystack for hint in HIRING_HINTS)
