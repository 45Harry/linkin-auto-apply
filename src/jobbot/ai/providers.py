"""Concrete AI providers and JSON extraction (spec 0001, AC-10).

Order is Ollama, Claude, Grok, Gemini. Ollama is local and free; Claude, Grok,
and Gemini are hosted and share a daily cap. Anthropic uses its own SDK; the
others are OpenAI compatible and use the OpenAI SDK pointed at their base URLs.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from ..config import Settings

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class ProviderError(Exception):
    pass


class Provider(Protocol):
    name: str
    hosted: bool

    def complete(self, *, system: str, user: str) -> str: ...


def extract_json(text: str) -> object:
    """Pull JSON out of a model reply, tolerating prose or code fences."""
    if not text or not text.strip():
        raise ProviderError("empty reply")
    candidates = [text.strip()]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ProviderError("no JSON in reply")


class OllamaProvider:
    name = "ollama"
    hosted = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def complete(self, *, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(
            base_url=f"{self._settings.ollama_url.rstrip('/')}/v1",
            api_key="ollama",
            timeout=self._settings.ai_ollama_timeout_seconds,
        )
        reply = client.chat.completions.create(
            model=self._settings.ollama_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return reply.choices[0].message.content or ""


class ClaudeProvider:
    name = "claude"
    hosted = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def complete(self, *, system: str, user: str) -> str:
        import anthropic

        client = anthropic.Anthropic(
            api_key=self._settings.anthropic_api_key,
            timeout=self._settings.ai_hosted_timeout_seconds,
        )
        message = client.messages.create(
            model=self._settings.claude_model,
            max_tokens=4096,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )


class OpenAiCompatibleProvider:
    """Grok and Gemini, both reachable through an OpenAI compatible endpoint."""

    hosted = True

    def __init__(self, *, name: str, base_url: str, api_key: str, model: str, timeout: int) -> None:
        self.name = name
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def complete(self, *, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(base_url=self._base_url, api_key=self._api_key, timeout=self._timeout)
        reply = client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return reply.choices[0].message.content or ""


class GrokProvider(OpenAiCompatibleProvider):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            name="grok",
            base_url="https://api.x.ai/v1",
            api_key=settings.xai_api_key or "",
            model=settings.grok_model,
            timeout=settings.ai_hosted_timeout_seconds,
        )


class GeminiProvider(OpenAiCompatibleProvider):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            name="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=settings.gemini_api_key or "",
            model=settings.gemini_model,
            timeout=settings.ai_hosted_timeout_seconds,
        )


def build_providers(settings: Settings) -> list[Provider]:
    """Providers in order, including only hosted ones that have a key configured."""
    providers: list[Provider] = [OllamaProvider(settings)]
    if settings.anthropic_api_key:
        providers.append(ClaudeProvider(settings))
    if settings.xai_api_key:
        providers.append(GrokProvider(settings))
    if settings.gemini_api_key:
        providers.append(GeminiProvider(settings))
    return providers


def build_criteria_providers(settings: Settings) -> list[Provider]:
    """Criteria order for the profile refresh: hosted first, then the small local model.

    A small local model is weak at reading a whole CV (spec 0001, AC-11), so Ollama is
    the last resort here, unlike item parsing where it is tried first.
    """
    providers: list[Provider] = []
    if settings.anthropic_api_key:
        providers.append(ClaudeProvider(settings))
    if settings.xai_api_key:
        providers.append(GrokProvider(settings))
    if settings.gemini_api_key:
        providers.append(GeminiProvider(settings))
    providers.append(OllamaProvider(settings))
    return providers
