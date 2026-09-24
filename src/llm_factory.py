"""Three-tier LLM client: FakeLLM when no key, RealLLM when a key is present."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from anthropic import APIError as AnthropicAPIError
from anthropic import AuthenticationError as AnthropicAuthenticationError
from anthropic import RateLimitError as AnthropicRateLimitError

from real_llm import RealLLM

_ROOT = Path(__file__).resolve().parents[1]
_TESTS = _ROOT / "tests"
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from fake_llm import FakeLLM  # noqa: E402

logger = logging.getLogger("agentic")

_PLACEHOLDERS = {"", "sk-ant-xxx", "your-key-here", "changeme"}

AUTH_MESSAGE = (
    "The model provider rejected the API key. "
    "Set a valid ANTHROPIC_API_KEY, or unset it "
    "to run in demo mode."
)
RATE_MESSAGE = (
    "The provider is rate-limiting requests. "
    "Retry in a few seconds."
)


def _scripted_complete(prompt: str) -> str:
    """Deterministic FakeLLM payloads that satisfy each module's contract."""
    lower = prompt.lower()

    if "return json: {\"score\"" in lower or (
        "output to evaluate" in lower and "critique" in lower
    ):
        return json.dumps({
            "score": 0.86,
            "critique": "Meets the stated criteria in this demo run.",
        })

    if "return json: {\"scores\"" in lower or (
        "proposals:" in lower and "critique" in lower
    ):
        numbered = re.findall(r"^\s*(\d+)\.\s", prompt, flags=re.M)
        n = len(numbered) or 3
        scores = [
            {
                "index": i,
                "score": round(0.9 - i * 0.08, 2),
                "critique": "Scripted demo critique.",
            }
            for i in range(n)
        ]
        return json.dumps({"scores": scores})

    if "complete the task. return json only" in lower and "confidence" in lower:
        return json.dumps({
            "answer": "Scripted demo answer from the cheap-capable path.",
            "confidence": 0.91,
        })

    if "decide on this user request" in lower:
        return json.dumps({
            "answer": "Scripted demo decision: proceed with a low-risk action.",
            "confidence": 0.88,
            "action": "note",
        })

    if "schema:" in lower and "text:" in lower:
        props = re.findall(
            r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*\{\s*"type"',
            prompt,
        )
        data: dict[str, Any] = {}
        for name in props:
            if "age" in name.lower() or name.lower() == "count":
                data[name] = 36
            elif "name" in name.lower() or "title" in name.lower():
                data[name] = "Ada Lovelace"
            else:
                data[name] = "demo"
        if not data:
            data = {"name": "Ada Lovelace", "age": 36}
        return json.dumps(data)

    if "available tools:" in lower or '"final"' in lower:
        return json.dumps({
            "thought": "The goal can be answered directly in demo mode.",
            "final": "Scripted ReAct final answer.",
        })

    if "summarize these conversation turns" in lower:
        return "Scripted long-term memory summary of earlier turns."

    if "synthesize the best final answer" in lower:
        return "Scripted debate synthesis: the winning proposal is sufficient."

    if "answer this question:" in lower:
        return "Scripted proposer answer for the debate demo."

    if "complete the task." in lower or "improve your answer" in lower:
        return "Scripted self-eval output: idempotency means repeating a request does not change the result."

    return "Scripted demo response (no live model key configured)."


class _DemoFakeLLM(FakeLLM):
    """FakeLLM subclass that never exhausts; responses follow module contracts."""

    def __init__(self) -> None:
        super().__init__(responses=["unused"], name="fake-llm")

    def complete(self, prompt: str) -> str:
        resp = _scripted_complete(prompt)
        self.calls.append({"prompt": prompt, "response": resp, "error": None})
        return resp


@lru_cache(maxsize=1)
def get_llm() -> tuple[Any, str]:
    """Return (client, mode). mode is "fake" or "real"."""
    key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if key in _PLACEHOLDERS or key.lower().startswith("sk-ant-xxx"):
        logger.info("LLM mode: fake (no valid ANTHROPIC_API_KEY set)")
        return _DemoFakeLLM(), "fake"
    logger.info("LLM mode: real")
    return RealLLM(key), "real"


def reload_llm() -> None:
    get_llm.cache_clear()


__all__ = [
    "get_llm",
    "reload_llm",
    "AnthropicAPIError",
    "AnthropicAuthenticationError",
    "AnthropicRateLimitError",
    "AUTH_MESSAGE",
    "RATE_MESSAGE",
]
