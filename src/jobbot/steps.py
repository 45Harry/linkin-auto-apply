"""The result shape every cycle step returns."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepResult:
    ok: bool
    error: str | None = None
    summary: dict[str, object] = field(default_factory=dict)
