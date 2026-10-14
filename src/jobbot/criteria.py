"""Criteria access. Criteria are generated in a later slice (AC-11); until then this
reads `data/criteria.json` when present and otherwise returns empty lists, so the
light filter works with whatever is configured and excludes nothing by default.

See the spec's `data/criteria.json` shape.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("jobbot.criteria")


@dataclass
class Criteria:
    titles: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    seniority: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)


def criteria_path(data_dir: Path) -> Path:
    return data_dir / "criteria.json"


def load(data_dir: Path) -> Criteria:
    path = criteria_path(data_dir)
    if not path.exists():
        return Criteria()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("criteria.json unreadable", extra={"error": str(exc)})
        return Criteria()
    return Criteria(
        titles=list(payload.get("titles", [])),
        keywords=list(payload.get("keywords", [])),
        locations=list(payload.get("locations", [])),
        seniority=list(payload.get("seniority", [])),
        exclude_keywords=list(payload.get("exclude_keywords", [])),
    )
