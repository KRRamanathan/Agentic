"""Compose the ten agent modules into one streaming pipeline."""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any, Callable

from pydantic import BaseModel, Field

from debate_system import Debate
from self_eval import SelfEvalAgent
from structured_output import StructuredAgent


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


class ExtractSchema(BaseModel):
    title: str = ""
    total: float | None = None
    summary: str = Field(default="")


class AgentPipeline:
    _pending: dict[str, dict[str, Any]] = {}

    def __init__(
        self,
        llm,
        tracer,
        memory,
        router,
        hitl,
        tools: dict[str, Callable],
        protected_actions: frozenset = frozenset({"delete", "send_email", "refund"}),
    ) -> None:
        self.llm = llm
        self.tracer = tracer
        self.memory = memory
        self.router = router
        self.hitl = hitl
        self.tools = dict(tools)
        self.protected_actions = frozenset(protected_actions)

    def run_stream(self, goal: str, scopes) -> Iterator[dict]:
        scopes = set(scopes or [])
        t0 = time.perf_counter()
        stage_count = 0
        model_name = "auto"
        answer = ""
        attempts = 0
        cost0 = float(getattr(self.llm, "total_cost", 0.0) or 0.0)

        if hasattr(self.tracer, "spans"):
            self.tracer.spans.clear()

        try:
            with self.tracer.span("memory_recall"):
                t = time.perf_counter()
                recalled = self.memory.recall(goal)
            yield _round({
                "stage": "memory_recall",
                "status": "ok",
                "duration_ms": (time.perf_counter() - t) * 1000,
                "payload": {"recalled": recalled},
            })
            stage_count += 1
        except Exception as exc:
            yield _round({"stage": "memory_recall", "status": "error", "message": str(exc)})
            return

        try:
            with self.tracer.span("cost_route"):
                t = time.perf_counter()
                force = getattr(self, "_force_model", None)
                mapping = {
                    "small": "haiku-sim",
                    "medium": "sonnet",
                    "large": "sonnet",
                }
                if force and force.lower() not in {"auto", ""}:
                    model_name = mapping.get(force.lower(), force)
                    if model_name not in self.router.models:
                        model_name = self.router.route(goal)
                else:
                    model_name = self.router.route(goal)
                cfg = self.router.models[model_name]
                cost_per_call = cfg.cost_per_call
            yield _round({
                "stage": "cost_route",
                "status": "ok",
                "duration_ms": (time.perf_counter() - t) * 1000,
                "payload": {"model": model_name, "cost_per_call": cost_per_call},
            })
            stage_count += 1
        except Exception as exc:
            yield _round({"stage": "cost_route", "status": "error", "message": str(exc)})
            return

        try:
            with self.tracer.span("react_loop"):
                for event, maybe_answer, maybe_action, n_attempts in self._react(goal, scopes):
                    attempts = n_attempts
                    if maybe_answer is not None:
                        answer = maybe_answer
                    yield _round(event)
                    if event.get("status") == "error":
                        return
                stage_count += 1
        except Exception as exc:
            yield _round({"stage": "react_loop", "status": "error", "message": str(exc)})
            return

        pause, reason, action = self._should_pause(goal, answer)
        if pause:
            ticket = str(uuid.uuid4())
            AgentPipeline._pending[ticket] = {
                "goal": goal,
                "answer": answer,
                "model": model_name,
                "t0": t0,
                "stage_count": stage_count,
                "attempts": attempts,
                "cost0": cost0,
                "scopes": scopes,
            }
            yield _round({
                "stage": "hitl_pause",
                "status": "pending",
                "ticket": ticket,
                "reason": reason,
                "action": action,
            })
            return

        yield from self._finish(goal, answer, model_name, t0, stage_count, attempts, cost0)

    def resume_stream(self, ticket: str, approved: bool, human_note: str = "") -> Iterator[dict]:
        pending = AgentPipeline._pending.pop(ticket, None)
        if pending is None:
            yield _round({
                "stage": "hitl_pause",
                "status": "error",
                "message": f"Ticket {ticket!r} not found or already resolved",
            })
            return

        if not approved:
            yield from self._finish(
                pending["goal"],
                pending["answer"] if human_note else "Aborted by human reviewer.",
                pending["model"],
                pending["t0"],
                pending["stage_count"],
                pending["attempts"],
                pending["cost0"],
                answer_override="Aborted by human reviewer." if not approved else None,
            )
            return

        extra = f" Human note: {human_note}" if human_note else ""
        answer = f"{pending['answer']}{extra}"
        yield from self._finish(
            pending["goal"],
            answer,
            pending["model"],
            pending["t0"],
            pending["stage_count"],
            pending["attempts"],
            pending["cost0"],
        )

    def _finish(
        self,
        goal: str,
        answer: str,
        model_name: str,
        t0: float,
        stage_count: int,
        attempts: int,
        cost0: float,
        answer_override: str | None = None,
    ) -> Iterator[dict]:
        final_answer = answer_override if answer_override is not None else answer
        try:
            with self.tracer.span("memory_write"):
                t = time.perf_counter()
                self.memory.add_turn(f"goal: {goal}")
                self.memory.add_turn(f"answer: {final_answer}")
            yield _round({
                "stage": "memory_write",
                "status": "ok",
                "duration_ms": (time.perf_counter() - t) * 1000,
            })
            stage_count += 1
        except Exception as exc:
            yield _round({"stage": "memory_write", "status": "error", "message": str(exc)})
            return

        total_cost = float(getattr(self.llm, "total_cost", 0.0) or 0.0) - cost0
        spans = list(getattr(self.tracer, "spans", []))
        yield _round({
            "stage": "done",
            "status": "ok",
            "answer": final_answer,
            "total_cost": total_cost,
            "total_time_ms": (time.perf_counter() - t0) * 1000,
            "stages": stage_count + 1,
            "model": model_name,
            "attempts": attempts,
            "spans": spans,
        })

    def _should_pause(self, goal: str, answer: str) -> tuple[bool, str, str]:
        lowered = f"{goal} {answer}".lower()
        for action in self.protected_actions:
            if action.replace("_", " ") in lowered or action in lowered:
                return True, "protected_action", action
        try:
            raw = self.hitl.handle(
                "Decide on this user request. Return JSON only with keys "
                'answer (string), confidence (0-1 float), action (string or null).\n'
                f"Request: {goal}\nDraft: {answer}"
            )
            if raw.get("status") == "pending":
                # Convert HITL ticket to pipeline pause (store already ours)
                return True, str(raw.get("reason") or "low_confidence"), "review"
        except Exception:
            pass
        return False, "", ""

    def _react(self, goal: str, scopes: set[str]):
        del scopes
        max_iterations = 5
        trace: list[dict] = []
        answer = ""
        last_action = None
        attempts = 0

        for i in range(max_iterations):
            attempts = i + 1
            prompt = self._react_prompt(goal, trace)
            raw = self.llm.complete(prompt)
            try:
                decision = json.loads(raw)
            except json.JSONDecodeError:
                trace.append({
                    "thought": None,
                    "action": None,
                    "observation": "ERROR: invalid decision format",
                })
                yield (
                    {
                        "stage": "react_loop",
                        "status": "running",
                        "iteration": i + 1,
                        "thought": None,
                        "tool": None,
                        "args": None,
                        "observation": "ERROR: invalid decision format",
                    },
                    None,
                    None,
                    attempts,
                )
                continue

            if not isinstance(decision, dict):
                continue

            thought = decision.get("thought", "")
            if "final" in decision:
                answer = str(decision.get("final") or "")
                yield (
                    {
                        "stage": "react_loop",
                        "status": "running",
                        "iteration": i + 1,
                        "thought": thought,
                        "tool": None,
                        "args": None,
                        "observation": None,
                    },
                    answer,
                    last_action,
                    attempts,
                )
                return

            action = decision.get("action")
            args = decision.get("args") or {}
            last_action = action
            if action not in self.tools:
                obs = f"ERROR: unknown tool {action!r}"
            elif not isinstance(args, dict):
                obs = "ERROR: 'args' must be a JSON object"
            else:
                try:
                    result = self.tools[action](**args)
                    obs = result if isinstance(result, str) else json.dumps(result, default=str)
                    if isinstance(result, dict) and "answer" in result:
                        answer = str(result["answer"])
                    elif isinstance(result, dict) and "output" in result:
                        answer = str(result["output"])
                    else:
                        answer = obs
                except Exception as exc:
                    obs = f"ERROR: {exc}"

            trace.append({
                "thought": thought,
                "action": action,
                "observation": obs,
            })
            yield (
                {
                    "stage": "react_loop",
                    "status": "running",
                    "iteration": i + 1,
                    "thought": thought,
                    "tool": action,
                    "args": args if isinstance(args, dict) else None,
                    "observation": obs,
                },
                answer,
                action,
                attempts,
            )

        if not answer:
            answer = " | ".join(
                str(s.get("observation")) for s in trace if s.get("observation")
            ) or "no observations"

    def _react_prompt(self, goal: str, trace: list[dict]) -> str:
        trace_text = "\n".join(
            f"Thought: {s.get('thought')} | Action: {s.get('action')} | "
            f"Observation: {s.get('observation')}"
            for s in trace
        ) or "(empty)"
        return (
            f"Goal: {goal}\n\n"
            f"Available tools: {sorted(self.tools)}\n\n"
            "Use extract when the goal is to pull structured fields (totals, names) from text.\n"
            "Use debate when the goal is a comparison or judgment between options.\n"
            "Use self_eval when the goal is to write or refine a definition or short answer.\n"
            "Otherwise finish with a final answer.\n\n"
            f"Trace so far:\n{trace_text}\n\n"
            "Reply with JSON only.\n"
            '  • To call a tool: {"thought": "...", "action": "<tool>", "args": {...}}\n'
            '  • To finish:      {"thought": "...", "final": "<answer>"}'
        )
