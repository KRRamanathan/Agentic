"""Compose the ten agent modules into one streaming pipeline."""
from __future__ import annotations

import json
import os
import time
import uuid

from pydantic import BaseModel, Field

from debate_system import Debate
from self_eval import SelfEvalAgent
from src.llm_factory import (
    AUTH_MESSAGE,
    RATE_MESSAGE,
    AnthropicAPIError,
    AnthropicAuthenticationError,
    AnthropicRateLimitError,
    GeminiAPIError,
    GeminiAuthError,
    GeminiRateLimitError,
    get_llm,
)
from structured_output import StructuredAgent


def _provider_event(stage: str, exc: BaseException) -> dict:
    if isinstance(exc, (AnthropicAuthenticationError, GeminiAuthError)):
        return {"stage": stage, "status": "unavailable", "message": AUTH_MESSAGE}
    if isinstance(exc, (AnthropicRateLimitError, GeminiRateLimitError)):
        return {"stage": stage, "status": "unavailable", "message": RATE_MESSAGE}
    if isinstance(exc, (AnthropicAPIError, GeminiAPIError)):
        msg = getattr(exc, "message", None) or str(exc)
        if "x-api-key" in str(msg).lower() or "api key" in str(msg).lower() or "authentication" in str(msg).lower():
            return {"stage": stage, "status": "unavailable", "message": AUTH_MESSAGE}
        return {"stage": stage, "status": "unavailable", "message": f"The model provider returned an error: {msg}"}
    text = str(exc)
    if "x-api-key" in text.lower() or "authentication_error" in text.lower():
        return {"stage": stage, "status": "unavailable", "message": AUTH_MESSAGE}
    return {"stage": stage, "status": "error", "message": text}


_TASK_VERBS = (
    "write", "plan", "design", "compare", "extract", "analyze",
    "construct", "architect", "evaluate", "debate",
)


def _requires_tool(goal: str) -> bool:
    words = [w for w in goal.replace(",", " ").split() if w]
    lowered = goal.lower()
    if len(words) > 10:
        return True
    if any(verb in lowered for verb in _TASK_VERBS):
        return True
    if any(token in lowered for token in ("better", "versus", " vs ", " or ")):
        return True
    return False


def _display_model(router_name: str) -> str:
    client, mode = get_llm()
    if mode == "fake":
        return "fake-llm"
    return getattr(client, "name", None) or os.getenv("GEMINI_MODEL") or "gemini-3.6-flash"


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
    invoice_number: str = ""
    total: float | None = None
    status: str = ""
    summary: str = Field(default="")


def _fill_goal_args(action: str, args: dict, goal: str) -> dict:
    filled = dict(args)
    if action == "debate":
        filled["question"] = goal
    elif action == "extract":
        filled["text"] = goal
    elif action == "self_eval":
        filled["task"] = goal
    return filled


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
        self.tracer = getattr(llm, "tracer", None) or tracer
        self.tracer.clock = time.monotonic
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
            yield _round(_provider_event("memory_recall", exc))
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
                model_name = _display_model(model_name)
            yield _round({
                "stage": "cost_route",
                "status": "ok",
                "duration_ms": (time.perf_counter() - t) * 1000,
                "payload": {"model": model_name, "cost_per_call": cost_per_call},
            })
            stage_count += 1
        except Exception as exc:
            yield _round(_provider_event("cost_route", exc))
            return

        try:
            with self.tracer.span("react_loop"):
                for event, maybe_answer, maybe_action, n_attempts in self._react(goal, scopes):
                    attempts = n_attempts
                    if maybe_answer is not None:
                        answer = maybe_answer
                    yield _round(event)
                    if event.get("status") == "error" or event.get("status") == "unavailable":
                        return
                stage_count += 1
        except Exception as exc:
            yield _round(_provider_event("react_loop", exc))
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
        spans = []
        for raw in list(getattr(self.tracer, "spans", [])):
            seconds = float(raw.get("duration") or 0.0)
            spans.append({
                "name": raw.get("name"),
                "duration": round(seconds, 6),
                "duration_ms": round(seconds * 1000, 3),
                "parent": raw.get("parent"),
                "model": model_name,
            })
        event = _round({
            "stage": "done",
            "status": "ok",
            "answer": final_answer,
            "total_cost": total_cost,
            "total_time_ms": (time.perf_counter() - t0) * 1000,
            "stages": stage_count + 1,
            "model": model_name,
            "attempts": attempts,
        })
        event["spans"] = spans
        yield event

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
        tool_used = False

        for i in range(max_iterations):
            attempts = i + 1
            last_iter = i == max_iterations - 1
            if last_iter and not tool_used and _requires_tool(goal):
                action, args, thought, obs, answer = self._force_self_eval(goal)
                last_action = action
                yield (
                    {
                        "stage": "react_loop",
                        "status": "running",
                        "iteration": i + 1,
                        "thought": thought,
                        "tool": action,
                        "args": args,
                        "observation": obs,
                    },
                    answer,
                    action,
                    attempts,
                )
                return
            prompt = self._react_prompt(goal, trace)
            try:
                raw = self.llm.complete(prompt)
            except Exception as exc:
                yield (_round(_provider_event("react_loop", exc)), None, None, attempts)
                return
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
                if (not tool_used) and _requires_tool(goal) and not last_iter:
                    trace.append({
                        "thought": thought,
                        "action": None,
                        "observation": (
                            "ERROR: this goal is not a trivial one-liner. "
                            "Call extract, debate, or self_eval before finishing."
                        ),
                    })
                    continue
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
                args = _fill_goal_args(action, args, goal)
                try:
                    result = self.tools[action](**args)
                    tool_used = True
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

        if not tool_used and _requires_tool(goal):
            action, args, thought, obs, answer = self._force_self_eval(goal)
            yield (
                {
                    "stage": "react_loop",
                    "status": "running",
                    "iteration": max_iterations,
                    "thought": thought,
                    "tool": action,
                    "args": args,
                    "observation": obs,
                },
                answer,
                action,
                attempts,
            )
            return

        if not answer:
            answer = " | ".join(
                str(s.get("observation")) for s in trace if s.get("observation")
            ) or "no observations"

    def _force_self_eval(self, goal: str):
        thought = "No tool was selected in time; running self_eval to produce a refined answer."
        args = {
            "task": goal,
            "criteria": "Accurate, complete, and useful for the stated goal.",
        }
        result = self.tools["self_eval"](**args)
        obs = result if isinstance(result, str) else json.dumps(result, default=str)
        if isinstance(result, dict) and result.get("output"):
            answer = str(result["output"])
        elif isinstance(result, dict) and result.get("answer"):
            answer = str(result["answer"])
        else:
            answer = obs
        return "self_eval", args, thought, obs, answer

    def _react_prompt(self, goal: str, trace: list[dict]) -> str:
        trace_text = "\n".join(
            f"Thought: {s.get('thought')} | Action: {s.get('action')} | "
            f"Observation: {s.get('observation')}"
            for s in trace
        ) or "(empty)"
        must_tool = (
            "This goal is NOT a trivial one-liner. You MUST call a tool on this "
            "iteration. Do not return \"final\" yet."
            if _requires_tool(goal) and not any(s.get("action") for s in trace)
            else ""
        )
        return (
            f"Goal: {goal}\n\n"
            "Available tools:\n"
            '- "extract"   — pull structured fields from text. '
            'args: {"text": "<source text>"}\n'
            '- "debate"    — get multiple perspectives and synthesize. '
            'args: {"question": "<question>"}\n'
            '- "self_eval" — generate, judge, refine iteratively. '
            'args: {"task": "<task>", "criteria": "<quality bar>"}\n\n'
            "Routing rules:\n"
            "- Use extract when the goal is pulling data from provided text "
            "(invoices, totals, names).\n"
            "- Use debate for questions with multiple defensible answers "
            "(comparisons, trade-offs, \"better than\").\n"
            "- Use self_eval for open-ended creative or planning tasks "
            "(write, design, architecture, definitions).\n"
            "- Forbid answering directly unless the goal is a trivial one-liner "
            '(for example "say hello").\n'
            "- If the goal is longer than about 10 words or contains a task verb "
            "(write, plan, design, compare, extract, analyze), you MUST call a "
            "tool on the first iteration.\n"
            f"{must_tool}\n\n"
            "For the question, text, and task arguments, copy the user's goal "
            "verbatim. Do not paraphrase, shorten, or summarize. Include every word.\n"
            "When you decide to finish, your 'final' field MUST synthesize the "
            "actual content from the tool observations you have received. Do not "
            "output a generic sentence. Do not say 'the tool result is enough.' "
            "Your final answer must contain the substance of what the tools "
            "returned — names, values, arguments, or conclusions the tools "
            "produced.\n\n"
            f"Trace so far:\n{trace_text}\n\n"
            "Reply with JSON only.\n"
            '  • To call a tool: {"thought": "...", "action": "<tool>", "args": {...}}\n'
            '  • To finish:      {"thought": "...", "final": "<answer>"}'
        )
