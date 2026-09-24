"""Project 10 — Tracing, Accounting, and Loop Detection.
Instrument an agent's LLM calls with named spans, per-call cost/latency
accounting, and a repeated-prompt alarm.
"""
import time
from contextlib import contextmanager


class Tracer:
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.spans: list[dict] = []
        self._stack: list[str] = []

    @contextmanager
    def span(self, name: str):
        parent = self._stack[-1] if self._stack else None
        self._stack.append(name)
        start = self.clock()
        try:
            yield
        finally:
            duration = self.clock() - start
            self._stack.pop()
            self.spans.append({
                "name": name,
                "duration": duration,
                "parent": parent,
            })


class InstrumentedLLM:
    def __init__(
        self,
        llm,
        tracer: Tracer,
        cost_per_call: float = 0.01,
        loop_threshold: int = 3,
    ):
        self.llm = llm
        self.tracer = tracer
        self.cost_per_call = cost_per_call
        self.loop_threshold = loop_threshold
        self.total_cost: float = 0.0
        self.call_count: int = 0
        self.alerts: list[dict] = []
        self._prompt_counts: dict[str, int] = {}

    def complete(self, prompt: str) -> str:
        self.call_count += 1
        self.total_cost += self.cost_per_call

        count = self._prompt_counts.get(prompt, 0) + 1
        self._prompt_counts[prompt] = count
        if count % self.loop_threshold == 0:
            self.alerts.append({
                "type": "loop",
                "prompt": prompt,
                "count": count,
            })

        with self.tracer.span("llm.complete"):
            return self.llm.complete(prompt)

    def report(self) -> dict:
        llm_spans = [
            s for s in self.tracer.spans
            if s["name"] == "llm.complete"
        ]
        avg_latency = (
            sum(s["duration"] for s in llm_spans) / len(llm_spans)
            if llm_spans else 0.0
        )
        return {
            "calls": self.call_count,
            "total_cost": self.total_cost,
            "avg_latency": avg_latency,
            "alerts": self.alerts,
        }
