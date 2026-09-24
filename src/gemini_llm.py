"""Gemini client with the same complete(prompt) -> str surface as FakeLLM / RealLLM."""
from __future__ import annotations

import os
import re
import time

import httpx

DEFAULT_MODEL = "gemini-3.6-flash"
_RETIRED = ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro")
_REDIRECT = re.compile(r"use models/([a-zA-Z0-9._-]+)", re.I)


class GeminiAuthError(Exception):
    """Raised when Gemini rejects the API key."""


class GeminiRateLimitError(Exception):
    """Raised when Gemini rate-limits."""


class GeminiAPIError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _model_name(explicit: str | None) -> str:
    raw = (
        explicit
        or os.getenv("GEMINI_MODEL")
        or DEFAULT_MODEL
    )
    lowered = raw.lower()
    if (
        lowered.startswith("claude")
        or "sonnet" in lowered
        or "haiku" in lowered
        or any(tag in lowered for tag in _RETIRED)
    ):
        return DEFAULT_MODEL
    return raw


def _strip_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S | re.I)
    if fence:
        return fence.group(1).strip()
    return text


class GeminiLLM:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "")
        )
        self.model = _model_name(model)
        self.name = self.model
        self.max_tokens = max_tokens

    def _post(self, url: str, body: dict) -> httpx.Response:
        return httpx.post(
            url,
            params={"key": self.api_key},
            headers={"x-goog-api-key": self.api_key},
            json=body,
            timeout=120.0,
        )

    def complete(self, prompt: str) -> str:
        queue = [self.model]
        tried: set[str] = set()
        last_error: Exception | None = None
        while queue:
            model = queue.pop(0)
            if model in tried or any(tag in model for tag in _RETIRED):
                continue
            tried.add(model)
            try:
                text = self._generate(model, prompt)
                self.model = model
                self.name = model
                return text
            except GeminiAuthError:
                raise
            except GeminiRateLimitError:
                raise
            except GeminiAPIError as exc:
                last_error = exc
                redirect = _REDIRECT.search(str(exc))
                if redirect:
                    nxt = redirect.group(1)
                    if nxt not in tried:
                        queue.insert(0, nxt)
                    continue
                raise
        if last_error:
            raise last_error
        raise GeminiAPIError("Gemini returned an empty response")

    def _generate(self, model: str, prompt: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": 0.2,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        try:
            response = self._post(url, body)
        except httpx.HTTPError as exc:
            raise GeminiAPIError(str(exc)) from exc

        if response.status_code == 400 and "thinkingConfig" in response.text:
            body["generationConfig"].pop("thinkingConfig", None)
            response = self._post(url, body)

        if response.status_code == 503:
            for delay in (2.0, 4.0, 8.0):
                time.sleep(delay)
                response = self._post(url, body)
                if response.status_code != 503:
                    break

        if response.status_code in {401, 403}:
            raise GeminiAuthError(response.text[:300])
        if response.status_code == 429:
            raise GeminiRateLimitError(response.text[:300])
        if response.status_code == 503:
            raise GeminiRateLimitError(
                "The model is busy right now. Wait a few seconds and run again."
            )
        if response.status_code >= 400:
            raise GeminiAPIError(f"{response.status_code}: {response.text[:400]}")

        payload = response.json()
        error = payload.get("error")
        if isinstance(error, dict):
            status = str(error.get("status") or "")
            msg = str(error.get("message") or error)
            if "UNAUTHENTICATED" in status or "API_KEY" in msg.upper():
                raise GeminiAuthError(msg)
            raise GeminiAPIError(msg)

        parts: list[str] = []
        for candidate in payload.get("candidates") or []:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                text = part.get("text")
                if text:
                    parts.append(text)
        joined = _strip_fences("".join(parts))
        if not joined:
            raise GeminiAPIError("Gemini returned no text")
        return joined
