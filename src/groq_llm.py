"""Groq client with the same complete(prompt) -> str surface as the other LLMs."""
from __future__ import annotations

import os
import re

import httpx

from src.gemini_llm import GeminiAPIError, GeminiAuthError, GeminiRateLimitError

DEFAULT_MODEL = "openai/gpt-oss-120b"
_FALLBACKS = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
)
_URL = "https://api.groq.com/openai/v1/chat/completions"


def _strip_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S | re.I)
    if fence:
        return fence.group(1).strip()
    return text


class GroqLLM:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("GROQ_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "")
        self.model = model or os.getenv("GROQ_MODEL") or DEFAULT_MODEL
        self.name = self.model
        self.max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        last: Exception | None = None
        for model in (self.model, *[m for m in _FALLBACKS if m != self.model]):
            try:
                text = self._once(model, prompt)
                self.model = model
                self.name = model
                return text
            except GeminiAuthError:
                raise
            except GeminiRateLimitError:
                raise
            except GeminiAPIError as exc:
                last = exc
                if "model_not_found" in str(exc) or "does not exist" in str(exc):
                    continue
                raise
        if last:
            raise last
        raise GeminiAPIError("Groq returned no text")

    def _once(self, model: str, prompt: str) -> str:
        try:
            response = httpx.post(
                _URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": self.max_tokens,
                },
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise GeminiAPIError(str(exc)) from exc

        if response.status_code in {401, 403}:
            raise GeminiAuthError("The model provider rejected the API key.")
        if response.status_code == 429:
            raise GeminiRateLimitError("The provider is rate-limiting requests.")
        if response.status_code >= 400:
            raise GeminiAPIError(f"{response.status_code}: {response.text[:300]}")

        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise GeminiAPIError("Groq returned no choices")
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        content = _strip_fences(content)
        if not content:
            raise GeminiAPIError("Groq returned no text")
        return content
