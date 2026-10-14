"""Dedupe keys and the company match hash.

A dedupe key makes one job row per posting. A match hash lets the same role seen
through different sources become one row when a company is known. Posts with no
known company never use a match hash, so different authors' posts stay separate.
"""

from __future__ import annotations

import hashlib

from .normalize import city_from_location, normalize_company_name, normalize_text, normalize_url


def ats_dedupe_key(ats_type: str, ats_token: str, posting_id: str) -> str:
    return f"ats:{ats_type}:{ats_token}:{posting_id}"


def linkedin_job_key(job_id: str) -> str:
    return f"li:{job_id}"


def linkedin_post_key(activity_id: str) -> str:
    return f"post:{activity_id}"


def url_dedupe_key(url: str) -> str:
    return f"url:{normalize_url(url)}"


def match_hash(company_name: str, title: str, location: str | None) -> str:
    parts = [
        normalize_company_name(company_name),
        normalize_text(title),
        city_from_location(location),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
