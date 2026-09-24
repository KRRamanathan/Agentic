"""Project 2 — Bounded ReAct Agent.

Observe -> think -> act with a hard iteration cap, unknown-tool recovery,
and graceful degradation instead of infinite looping.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

ToolFn = Callable[..., Any]

DEFAULT_INSTRUCTIONS = (
    'Reply with JSON only.\n'
    '  • To call a tool: {"thought": "...", "action": "<tool>", "args": {...}}\n'
    '  • To finish:      {"thought": "...", "final": "<answer>"}'
)


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class ReActAgent:
    """Think-act-observe loop with a hard iteration cap.

    Errors are observations, not exceptions. The loop never raises and never
    runs past `max_iterations`.
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: dict[str, ToolFn],
        max_iterations: int = 5,
        *,
        instructions: str = DEFAULT_INSTRUCTIONS,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.llm = llm
        self.tools = dict(tools)
        self.max_iterations = max_iterations
        self.instructions = instructions
        self.trace: list[dict[str, Any]] = []

    def _build_prompt(self, goal: str) -> str:
        trace_text = "\n".join(
            f"Thought: {s.get('thought')} | "
            f"Action: {s.get('action')} | "
            f"Observation: {s.get('observation')}"
            for s in self.trace
        ) or "(empty)"
        return (
            f"Goal: {goal}\n\n"
            f"Available tools: {sorted(self.tools)}\n\n"
            f"Trace so far:\n{trace_text}\n\n"
            f"{self.instructions}"
        )

    def run(self, goal: str) -> dict[str, Any]:
        self.trace = []

        for i in range(self.max_iterations):
            raw = self.llm.complete(self._build_prompt(goal))

            try:
                decision = json.loads(raw)
            except json.JSONDecodeError:
                self.trace.append({
                    "thought": None,
                    "action": None,
                    "observation": "ERROR: invalid decision format",
                })
                continue

            if not isinstance(decision, dict):
                self.trace.append({
                    "thought": None,
                    "action": None,
                    "observation": "ERROR: invalid decision format",
                })
                continue

            thought = decision.get("thought", "")

            # ---- final answer -------------------------------------------
            if "final" in decision:
                self.trace.append({
                    "thought": thought,
                    "action": None,
                    "observation": None,
                })
                return {
                    "status": "done",
                    "answer": decision["final"],
                    "iterations": i + 1,
                }

            # ---- tool call ----------------------------------------------
            action = decision.get("action")
            args = decision.get("args") or {}

            if action not in self.tools:
                obs = f"ERROR: unknown tool {action!r}"
            elif not isinstance(args, dict):
                obs = "ERROR: 'args' must be a JSON object"
            else:
                try:
                    obs = str(self.tools[action](**args))
                except Exception as exc:  # noqa: BLE001
                    obs = f"ERROR: {exc}"
                    logger.info("tool %r failed: %s", action, exc)

            self.trace.append({
                "thought": thought,
                "action": action,
                "observation": obs,
            })

        # ---- graceful degradation --------------------------------------
        summary = " | ".join(
            step["observation"]
            for step in self.trace
            if step.get("observation")
        ) or "no observations"

        return {
            "status": "max_iterations",
            "answer": summary,
            "iterations": self.max_iterations,
        }
