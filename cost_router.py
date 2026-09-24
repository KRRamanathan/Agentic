"""Project 6 — Cost-Aware Router.

Route tasks to the cheapest capable model, keep a hard token budget,
escalate at most once if the cheap model isn't confident enough, and
report cost analytics that reconcile exactly with the ledger.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = frozenset({"analyze", "compare", "architecture", "multi-step", "prove"})


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class BudgetExceeded(RuntimeError):
    """Raised before any call that would push spend past the configured budget."""


def estimate_complexity(task: str) -> int:
    """Baseline complexity: word count + 10 per complexity keyword.

    Override via `CostRouter(..., complexity_fn=...)` if your domain needs a
    different scorer.
    """
    base = len(task.split())
    return base + 10 * sum(1 for kw in DEFAULT_KEYWORDS if kw in task.lower())


@dataclass(frozen=True)
class ModelConfig:
    client: LLMClient
    cost_per_call: float
    max_complexity: int

    def __post_init__(self) -> None:
        if self.cost_per_call < 0:
            raise ValueError("cost_per_call must be >= 0")
        if self.max_complexity < 0:
            raise ValueError("max_complexity must be >= 0")


class CostRouter:
    """Route each task to the cheapest model that can handle it.

    Budget is checked *before* every LLM call. Escalation happens at most once.
    Every call — including escalations — is recorded in the ledger.
    """

    def __init__(
        self,
        models: dict[str, ModelConfig],
        budget: float,
        confidence_exit: float = 0.8,
        *,
        complexity_fn: Callable[[str], int] | None = None,
    ) -> None:
        if not models:
            raise ValueError("at least one model is required")
        if budget < 0:
            raise ValueError("budget must be >= 0")
        self.models = dict(models)
        self.budget = budget
        self.confidence_exit = confidence_exit
        self._complexity = complexity_fn or estimate_complexity
        self.ledger: list[dict[str, Any]] = []
        self._lock = RLock()

    # ---- accounting -------------------------------------------------------
    def _spent(self) -> float:
        with self._lock:
            return sum(e["cost"] for e in self.ledger)

    def _record(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self.ledger.append(entry)

    # ---- routing ----------------------------------------------------------
    def route(self, task: str) -> str:
        complexity = self._complexity(task)
        with self._lock:
            capable = [
                (cfg.cost_per_call, name)
                for name, cfg in self.models.items()
                if cfg.max_complexity >= complexity
            ]
        if capable:
            return min(capable)[1]
        # Nothing claims to handle this complexity — fall back to the most capable.
        return max(self.models, key=lambda n: self.models[n].max_complexity)

    def llm_call(self, model_name: str, task: str) -> str:
        return self.models[model_name].client.complete(task)

    # ---- execution --------------------------------------------------------
    def run_task(self, task: str) -> dict[str, Any]:
        model_name = self.route(task)
        cfg = self.models[model_name]
        cost = cfg.cost_per_call

        if self._spent() + cost > self.budget:
            raise BudgetExceeded(
                f"budget {self.budget} would be exceeded by calling {model_name} "
                f"(already spent {self._spent():.4f})"
            )

        raw = self.llm_call(model_name, task)
        parsed = json.loads(raw)
        answer = parsed["answer"]
        confidence = float(parsed.get("confidence", 1.0))

        # Record the first call — it happened, budget must reflect it.
        self._record({
            "task": task,
            "model": model_name,
            "cost": cost,
            "escalated": False,
        })
        total_cost = cost
        final_model = model_name

        # Escalate at most once, budget-guarded.
        if confidence < self.confidence_exit:
            best = max(
                self.models,
                key=lambda n: self.models[n].max_complexity,
            )
            if best != model_name:
                best_cost = self.models[best].cost_per_call
                if self._spent() + best_cost <= self.budget:
                    raw2 = self.llm_call(best, task)
                    parsed2 = json.loads(raw2)
                    answer = parsed2["answer"]
                    total_cost += best_cost
                    final_model = best
                    self._record({
                        "task": task,
                        "model": best,
                        "cost": best_cost,
                        "escalated": True,
                    })
                else:
                    logger.info("escalation to %s skipped: budget", best)

        return {"answer": answer, "model": final_model, "cost": total_cost}

    # ---- analytics --------------------------------------------------------
    def analytics(self) -> dict[str, Any]:
        with self._lock:
            ledger = list(self.ledger)
        if not ledger:
            return {
                "total_cost": 0.0,
                "calls": 0,
                "by_model": {},
                "escalation_rate": 0.0,
            }
        by_model: dict[str, float] = {}
        for e in ledger:
            by_model[e["model"]] = by_model.get(e["model"], 0.0) + e["cost"]
        escalated = sum(1 for e in ledger if e["escalated"])
        return {
            "total_cost": sum(e["cost"] for e in ledger),
            "calls": len(ledger),
            "by_model": by_model,
            "escalation_rate": escalated / len(ledger),
        }
