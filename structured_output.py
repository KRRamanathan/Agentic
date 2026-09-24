"""Project 1 — Structured Output Agent.

Make LLM output reliable: enforce a Pydantic schema, retry on parse/validation
errors feeding the error back to the model, and log every failure.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

DEFAULT_PREAMBLE = (
    "You extract structured data. Return ONLY valid JSON matching the "
    "schema below. No markdown, no prose, no explanation."
)


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class ExtractionError(RuntimeError):
    """Raised when the LLM cannot produce schema-valid output within retries."""


def _default_json_extractor(raw: str) -> str:
    """Strip ```json fences and prose, keep the first {...} block."""
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 2:
            s = parts[1]
            if s.lower().startswith("json"):
                s = s[4:]
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        return s[start : end + 1]
    return s


class StructuredAgent:
    """Wrap an LLM call so its output is guaranteed schema-valid.

    On failure, the exact validation error is fed back into the next prompt.
    All failures are recorded on `self.failures` — nothing is lost.
    """

    def __init__(
        self,
        llm: LLMClient,
        schema: type[TModel],
        max_retries: int = 2,
        *,
        preamble: str = DEFAULT_PREAMBLE,
        json_extractor: Callable[[str], str] | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.llm = llm
        self.schema = schema
        self.max_retries = max_retries
        self.preamble = preamble
        self._extract = json_extractor or _default_json_extractor
        self.failures: list[dict[str, Any]] = []

    def build_prompt(self, text: str, previous_error: str | None = None) -> str:
        schema_json = json.dumps(
            self.schema.model_json_schema(), indent=2, ensure_ascii=False
        )
        prompt = (
            f"{self.preamble}\n\n"
            f"Schema:\n{schema_json}\n\n"
            f"Text:\n{text}"
        )
        if previous_error:
            prompt += (
                "\n\nYour previous response was rejected. Fix the issue and "
                f"return valid JSON only.\nReason: {previous_error}"
            )
        return prompt

    def extract(self, text: str) -> TModel:
        """Return a schema-valid instance, or raise ExtractionError."""
        previous_error: str | None = None

        for attempt in range(self.max_retries + 1):
            raw = self.llm.complete(self.build_prompt(text, previous_error))
            try:
                return self.schema.model_validate_json(self._extract(raw))
            except (ValueError, ValidationError) as exc:
                error_str = str(exc)
                self.failures.append({
                    "attempt": attempt,
                    "raw": raw,
                    "error": error_str,
                })
                logger.warning(
                    "extract attempt %d/%d failed: %s",
                    attempt + 1, self.max_retries + 1, error_str,
                )
                previous_error = error_str

        raise ExtractionError(
            f"Failed after {self.max_retries + 1} attempts. "
            f"Last error: {previous_error}"
        )
