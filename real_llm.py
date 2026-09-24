"""Live Anthropic Claude client with the same complete(prompt) -> str surface as FakeLLM."""
from __future__ import annotations

import os

from anthropic import Anthropic, APIError, APIStatusError


DEFAULT_MODEL = "claude-sonnet-4-6"


class LLMUnavailable(RuntimeError):
    """Raised when the live client cannot be used (missing key or API failure)."""


class RealLLM:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        self.model = model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.name = self.model
        self._client: Anthropic | None = None

    def _client_or_raise(self) -> Anthropic:
        if not self.api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        if self._client is None:
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def complete(self, prompt: str) -> str:
        try:
            message = self._client_or_raise().messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except LLMUnavailable:
            raise
        except APIStatusError as exc:
            raise LLMUnavailable(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except APIError as exc:
            raise LLMUnavailable(f"Anthropic API error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMUnavailable(f"Anthropic request failed: {exc}") from exc

        parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts)
