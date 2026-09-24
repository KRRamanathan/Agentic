"""Project 3 — Multi-Tool Orchestrator.
Dynamic tool registry, capability-based routing with priority conflict
resolution, permission scoping, and parallel execution.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    fn: Callable
    capabilities: set[str]
    required_scope: str | None = None
    priority: int = 0


class PermissionDenied(Exception):
    pass


class Orchestrator:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def resolve(self, capability: str) -> Tool:
        candidates = [
            t for t in self.tools.values()
            if capability in t.capabilities
        ]
        if not candidates:
            raise KeyError(f"No tool provides capability {capability!r}")
        return min(candidates, key=lambda t: (-t.priority, t.name))

    def execute(self, capability: str, scopes: set[str], **kwargs):
        tool = self.resolve(capability)
        if tool.required_scope and tool.required_scope not in scopes:
            raise PermissionDenied(
                f"Tool {tool.name!r} requires scope {tool.required_scope!r}"
            )
        return tool.fn(**kwargs)

    def execute_parallel(
        self, tasks: list[dict], scopes: set[str]
    ) -> list[dict]:
        if not tasks:
            return []

        def run(task: dict) -> dict:
            try:
                result = self.execute(
                    task["capability"],
                    scopes,
                    **task.get("kwargs", {}),
                )
                return {"ok": True, "result": result}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            return list(pool.map(run, tasks))
