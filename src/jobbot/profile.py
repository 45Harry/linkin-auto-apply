"""Profile refresh: turn the CV and LinkedIn PDFs plus the public GitHub profile
into `data/criteria.json`, and email the LinkedIn searches to save (spec 0001,
AC-11, AC-12).

Triggers (from the spec interface surface): on start, when a profile PDF changes
(checked on each run), and weekly for GitHub. Change detection is hash based, so
running it more often than needed is safe and idempotent.

The criteria file keeps exactly the documented shape. The per input hashes that
drive change detection live in a small sidecar `data/profile/refresh.json`, because
the GitHub snapshot hash must be remembered between the hourly checks without
re-fetching GitHub and without bloating `criteria.json`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

import httpx

from .ai.providers import build_criteria_providers
from .ai.router import AiRouter
from .ai.schemas import SearchCriteria
from .config import Settings
from .criteria import criteria_path
from .steps import StepResult
from .timeutil import now_utc, parse_iso, to_iso

log = logging.getLogger("jobbot.profile")

GITHUB_CHECK_INTERVAL = timedelta(days=7)
MAX_SEARCH_LINKS = 10
SENIORITY_VALUES = {"intern", "junior", "mid", "senior", "lead"}

CRITERIA_SYSTEM_PROMPT = (
    "You read a candidate's CV, LinkedIn profile, and public GitHub profile and "
    "produce job search criteria. Reply with JSON only."
)


# -- PDF and GitHub inputs --------------------------------------------------


def extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


class GitHubFetcher(Protocol):
    def snapshot(self, username: str) -> dict: ...


class HttpGitHubFetcher:
    """Reads a public GitHub profile: the user record plus non fork repos."""

    def __init__(self, token: str | None = None, *, client: httpx.Client | None = None) -> None:
        self._token = token
        self._client = client

    def snapshot(self, username: str) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        base = f"https://api.github.com/users/{username}"
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=20.0)
        try:
            user = client.get(base, headers=headers)
            user.raise_for_status()
            repos = client.get(
                f"{base}/repos",
                params={"per_page": 100, "sort": "pushed"},
                headers=headers,
            )
            repos.raise_for_status()
            return _shape_snapshot(user.json(), repos.json())
        finally:
            if owns_client:
                client.close()


def _shape_snapshot(user: dict, repos: list[dict]) -> dict:
    top: list[dict] = []
    for repo in repos:
        if repo.get("fork"):
            continue
        top.append(
            {
                "name": repo.get("name"),
                "description": repo.get("description"),
                "language": repo.get("language"),
                "topics": repo.get("topics") or [],
                "pushed_at": repo.get("pushed_at"),
                "stars": repo.get("stargazers_count"),
            }
        )
        if len(top) >= 30:
            break
    return {
        "login": user.get("login"),
        "name": user.get("name"),
        "bio": user.get("bio"),
        "company": user.get("company"),
        "location": user.get("location"),
        "blog": user.get("blog"),
        "public_repos": user.get("public_repos"),
        "followers": user.get("followers"),
        "top_repos": top,
    }


# -- hashing and state ------------------------------------------------------


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_json(value: object) -> str:
    return _hash(json.dumps(value, sort_keys=True, ensure_ascii=False))


def _state_path(data_dir: Path) -> Path:
    return data_dir / "profile" / "refresh.json"


@dataclass
class RefreshState:
    cv_hash: str = ""
    linkedin_hash: str = ""
    github_hash: str = ""
    github_checked_at: str | None = None
    missing_cv_alerted: bool = False


def _load_state(data_dir: Path) -> RefreshState:
    path = _state_path(data_dir)
    if not path.exists():
        return RefreshState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RefreshState()
    return RefreshState(
        cv_hash=payload.get("cv_hash", ""),
        linkedin_hash=payload.get("linkedin_hash", ""),
        github_hash=payload.get("github_hash", ""),
        github_checked_at=payload.get("github_checked_at"),
        missing_cv_alerted=bool(payload.get("missing_cv_alerted", False)),
    )


def _save_state(data_dir: Path, state: RefreshState) -> None:
    path = _state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "cv_hash": state.cv_hash,
                "linkedin_hash": state.linkedin_hash,
                "github_hash": state.github_hash,
                "github_checked_at": state.github_checked_at,
                "missing_cv_alerted": state.missing_cv_alerted,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _read_text(path: Path, read_pdf: Callable[[Path], str]) -> str:
    if not path.exists():
        return ""
    try:
        return read_pdf(path)
    except Exception as exc:  # noqa: BLE001 - a bad PDF must not crash the run
        log.warning("pdf read failed", extra={"path": str(path), "error": str(exc)})
        return ""


# -- criteria generation and writing ----------------------------------------


def _criteria_prompt(cv_text: str, linkedin_text: str, snapshot: dict | None) -> str:
    parts = ["CV:\n" + (cv_text or "(none)")]
    if linkedin_text:
        parts.append("LinkedIn profile:\n" + linkedin_text)
    if snapshot is not None:
        parts.append("GitHub profile:\n" + json.dumps(snapshot, ensure_ascii=False))
    parts.append(
        "Produce job search criteria: job titles to search for, keywords, locations "
        "(include remote when wanted), seniority levels, and keywords to exclude. "
        "Base every value only on the material above."
    )
    return "\n\n".join(parts)


def _clean_values(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = value.strip()
        if text and text.lower() not in {v.lower() for v in seen}:
            seen.append(text)
    return seen


def _clean_seniority(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = value.strip().lower()
        if text in SENIORITY_VALUES and text not in out:
            out.append(text)
    return out


def _alert_set_hash(criteria: SearchCriteria) -> str:
    titles = sorted({t.strip().lower() for t in criteria.titles if t.strip()})
    locations = sorted({loc.strip().lower() for loc in criteria.locations if loc.strip()})
    if not titles and not locations:
        return ""
    return _hash_json({"titles": titles, "locations": locations})


def _write_criteria(
    path: Path,
    criteria: SearchCriteria,
    *,
    sources_hash: str,
    provider: str,
    now: datetime,
    alerts_email_sent_for: str,
) -> dict:
    payload = {
        "titles": _clean_values(criteria.titles),
        "keywords": _clean_values(criteria.keywords),
        "locations": _clean_values(criteria.locations),
        "seniority": _clean_seniority(criteria.seniority),
        "exclude_keywords": _clean_values(criteria.exclude_keywords),
        "sources_hash": sources_hash,
        "alert_set_hash": _alert_set_hash(criteria),
        "alerts_email_sent_for": alerts_email_sent_for,
        "generated_at": to_iso(now),
        "generated_by": provider,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _load_criteria_raw(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# -- the LinkedIn searches email (AC-12) ------------------------------------


def _search_link(title: str, location: str) -> str:
    params = {"keywords": title, "f_TPR": "r86400"}
    if location:
        params["location"] = location
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def _search_pairs(payload: dict) -> list[tuple[str, str]]:
    titles = [t for t in payload.get("titles", []) if t.strip()]
    locations = [loc for loc in payload.get("locations", []) if loc.strip()]
    pairs: list[tuple[str, str]] = []
    for title in titles:
        if locations:
            for location in locations:
                pairs.append((title, location))
                if len(pairs) >= MAX_SEARCH_LINKS:
                    return pairs
        else:
            pairs.append((title, ""))
            if len(pairs) >= MAX_SEARCH_LINKS:
                return pairs
    return pairs


def _send_alerts_email(
    alert_sink: Callable[[str, str], None], criteria_file: Path, payload: dict
) -> bool:
    alert_set_hash = payload.get("alert_set_hash") or ""
    if not alert_set_hash or alert_set_hash == payload.get("alerts_email_sent_for"):
        return False
    pairs = _search_pairs(payload)
    if not pairs:
        return False
    lines = [
        "Save these LinkedIn searches once, set a daily alert on each, then you are done.",
        "",
    ]
    for title, location in pairs:
        where = f" in {location}" if location else ""
        lines.append(f"{title}{where} (open, set alert, daily)")
        lines.append(_search_link(title, location))
        lines.append("")
    alert_sink("[jobbot] LinkedIn searches to save", "\n".join(lines).strip() + "\n")
    payload["alerts_email_sent_for"] = alert_set_hash
    criteria_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


# -- the step ---------------------------------------------------------------


def _default_alert_sink(settings: Settings) -> Callable[[str, str], None]:
    from .alerts import send_alert

    def _sink(subject: str, body: str) -> None:
        send_alert(settings, subject=subject, body=body)

    return _sink


def run_profile_refresh(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
    router: AiRouter | None = None,
    github: GitHubFetcher | None = None,
    read_pdf: Callable[[Path], str] = extract_pdf_text,
    alert_sink: Callable[[str, str], None] | None = None,
) -> StepResult:
    now = now or now_utc()
    alert_sink = alert_sink or _default_alert_sink(settings)
    profile_dir = settings.profile_dir
    criteria_file = criteria_path(settings.data_dir)
    state = _load_state(settings.data_dir)

    cv_text = _read_text(profile_dir / "cv.pdf", read_pdf)
    linkedin_text = _read_text(profile_dir / "linkedin.pdf", read_pdf)
    if cv_text:
        state.missing_cv_alerted = False

    cv_hash = _hash(cv_text)
    linkedin_hash = _hash(linkedin_text)
    pdfs_changed = cv_hash != state.cv_hash or linkedin_hash != state.linkedin_hash

    raw = _load_criteria_raw(criteria_file)
    refresh_needed = raw is None or pdfs_changed

    username = (settings.github_username or "").strip()
    github_due = bool(username) and _github_due(now, state)
    snapshot: dict | None = None
    github_hash = state.github_hash
    github_changed = False
    if username and (refresh_needed or github_due):
        fetcher = github or HttpGitHubFetcher(settings.github_token)
        try:
            snapshot = fetcher.snapshot(username)
        except Exception as exc:  # noqa: BLE001 - network and API errors
            if refresh_needed:
                return StepResult(ok=False, error=f"github snapshot failed: {exc}")
            log.warning("github refresh failed", extra={"error": str(exc)})
        else:
            state.github_checked_at = to_iso(now)
            github_hash = _hash_json(snapshot)
            github_changed = github_hash != state.github_hash

    do_regen = refresh_needed or github_changed
    sources_hash = _hash(f"{cv_hash}|{linkedin_hash}|{github_hash}")
    summary: dict[str, object] = {
        "regenerated": False,
        "email": False,
        "cv": bool(cv_text),
        "github": bool(username),
        "sources_hash": sources_hash,
    }
    error: str | None = None

    if do_regen and not cv_text:
        summary["role_queries_skipped"] = True
        if not state.missing_cv_alerted:
            alert_sink(
                "[jobbot] no CV found",
                f"No CV at {profile_dir / 'cv.pdf'}. Role search queries are skipped "
                "until you add one. Company queries and other sources keep running.\n",
            )
            state.missing_cv_alerted = True
        if raw is None:
            _empty = SearchCriteria()
            _write_criteria(
                criteria_file,
                _empty,
                sources_hash=sources_hash,
                provider="",
                now=now,
                alerts_email_sent_for="",
            )
    elif do_regen:
        generated, provider = _generate(conn, settings, router, cv_text, linkedin_text, snapshot)
        if generated is None:
            error = "criteria generation failed for every provider"
        else:
            sent_for = (raw or {}).get("alerts_email_sent_for", "")
            payload = _write_criteria(
                criteria_file,
                generated,
                sources_hash=sources_hash,
                provider=provider or "",
                now=now,
                alerts_email_sent_for=sent_for,
            )
            summary["regenerated"] = True
            summary["provider"] = provider
            summary["titles"] = len(payload["titles"])
            summary["locations"] = len(payload["locations"])
            if _send_alerts_email(alert_sink, criteria_file, payload):
                summary["email"] = True

    if error is None:
        state.cv_hash = cv_hash
        state.linkedin_hash = linkedin_hash
    state.github_hash = github_hash
    _save_state(settings.data_dir, state)

    return StepResult(ok=error is None, error=error, summary=summary)


def _generate(
    conn: sqlite3.Connection,
    settings: Settings,
    router: AiRouter | None,
    cv_text: str,
    linkedin_text: str,
    snapshot: dict | None,
) -> tuple[SearchCriteria | None, str | None]:
    router = router or AiRouter(settings, conn, providers=build_criteria_providers(settings))
    user = _criteria_prompt(cv_text, linkedin_text, snapshot)
    return router.parse(user=user, model_cls=SearchCriteria, system=CRITERIA_SYSTEM_PROMPT)


def _github_due(now: datetime, state: RefreshState) -> bool:
    if not state.github_checked_at:
        return True
    try:
        last = parse_iso(state.github_checked_at)
    except ValueError:
        return True
    return now - last >= GITHUB_CHECK_INTERVAL
