"""Text and URL normalization used by dedupe and merge."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_LEGAL_SUFFIXES = {"pvt", "ltd", "private", "limited", "inc", "llc"}
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {
    "gclid",
    "fbclid",
    "trk",
    "trackingid",
    "refid",
    "originalSubdomain".lower(),
    "src",
    "ref",
    "gh_src",
    "lever-source",
}


def normalize_text(value: str) -> str:
    text = _PUNCT.sub(" ", value.lower())
    return _SPACES.sub(" ", text).strip()


def normalize_company_name(name: str) -> str:
    tokens = [t for t in normalize_text(name).split(" ") if t and t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


def city_from_location(location: str | None) -> str:
    if not location:
        return "remote"
    first = location.split(",")[0]
    city = normalize_text(first)
    if not city or "remote" in city:
        return "remote"
    return city


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_KEYS
        and not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))
