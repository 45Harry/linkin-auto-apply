"""The validated shapes the AI parser must return (spec 0001, AC-8, AC-9).

Every AI output is validated against one of these models before it touches the
database; invalid output counts as a provider failure (AC-10). Enum fields use
`None` rather than `"unknown"` so a later source can fill them (AC-5), except
where the source genuinely says unknown.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
Seniority = Literal["intern", "junior", "mid", "senior", "lead", "unknown"]
ApplyMethod = Literal["easy_apply", "ats_form", "email", "unknown"]


class ParsedJob(BaseModel):
    """One job the parser found in a listing or listing email."""

    is_job: bool = True
    title: str = ""
    company: str | None = None
    location: str | None = None
    work_mode: WorkMode | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    seniority: Seniority | None = None
    apply_method: ApplyMethod | None = None
    apply_target: str | None = None
    description: str | None = None
    posted_at: str | None = None
    url: str | None = None


class ParsedJobList(BaseModel):
    """A LinkedIn job alert email lists several postings at once."""

    jobs: list[ParsedJob] = Field(default_factory=list)


class ParsedPost(BaseModel):
    """A LinkedIn notification email, which usually carries only a snippet."""

    is_hiring_post: bool = False
    title: str | None = None
    company: str | None = None
    location: str | None = None
    posted_at: str | None = None
    job_url: str | None = None
    activity_id: str | None = None
    author_name: str | None = None
    author_linkedin_url: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class SearchCriteria(BaseModel):
    """Search criteria generated from the profile (spec 0001, AC-11)."""

    titles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)


SCHEMA_HINTS: dict[type[BaseModel], str] = {
    ParsedJobList: (
        'Return JSON: {"jobs": [ {"is_job": bool, "title": str, "company": str|null, '
        '"location": str|null, "work_mode": "remote"|"hybrid"|"onsite"|"unknown"|null, '
        '"salary_min": int|null, "salary_max": int|null, "salary_currency": str|null, '
        '"seniority": "intern"|"junior"|"mid"|"senior"|"lead"|null, '
        '"apply_method": "easy_apply"|"ats_form"|"email"|null, "apply_target": str|null, '
        '"description": str|null, "posted_at": ISO-8601 str|null, "url": str|null } ]}'
    ),
    ParsedPost: (
        'Return JSON: {"is_hiring_post": bool, "title": str|null, "company": str|null, '
        '"location": str|null, "posted_at": ISO-8601 str|null, "job_url": str|null, '
        '"activity_id": str|null, "author_name": str|null, "author_linkedin_url": str|null, '
        '"contact_email": str|null, "contact_phone": str|null }'
    ),
    ParsedJob: (
        'Return JSON: {"is_job": bool, "title": str, "company": str|null, "location": str|null, '
        '"work_mode": str|null, "salary_min": int|null, "salary_max": int|null, '
        '"salary_currency": str|null, "seniority": str|null, "apply_method": str|null, '
        '"apply_target": str|null, "description": str|null, "posted_at": str|null, "url": str|null}'
    ),
    SearchCriteria: (
        'Return JSON: {"titles": [str], "keywords": [str], "locations": [str], '
        '"seniority": ["intern"|"junior"|"mid"|"senior"|"lead"], "exclude_keywords": [str]}'
    ),
}
