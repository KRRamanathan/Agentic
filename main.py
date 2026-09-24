"""FastAPI surface over the ten agent modules. Modules are imported and wrapped only."""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field, ValidationError, create_model

from cost_router import BudgetExceeded, CostRouter, ModelConfig
from debate_system import Debate
from event_automation import EventProcessor
from hitl_approval import ApprovalAgent, UnknownTicket
from memory_agent import Memory
from observability import InstrumentedLLM, Tracer
from react_loop import ReActAgent
from real_llm import LLMUnavailable
from self_eval import SelfEvalAgent
from src.agent_pipeline_factory import build_pipeline
from src.llm_factory import (
    AUTH_MESSAGE,
    RATE_MESSAGE,
    AnthropicAPIError,
    AnthropicAuthenticationError,
    AnthropicRateLimitError,
    get_llm,
)
from structured_output import ExtractionError, StructuredAgent
from tool_orchestrator import Orchestrator, PermissionDenied, Tool

load_dotenv()

logger = logging.getLogger("agentic")
logging.basicConfig(level=logging.INFO)

TYPE_MAP = {"str": str, "int": int, "float": float, "bool": bool}


# ---------------------------------------------------------------------------
# Shared process state
# ---------------------------------------------------------------------------

class _DelegatingLLM:
    """Routes complete() through get_llm() so mode is chosen at call time."""

    def complete(self, prompt: str) -> str:
        client, _mode = get_llm()
        return client.complete(prompt)


class AppRuntime:
    def __init__(self) -> None:
        self.tracer = Tracer()
        self.llm = InstrumentedLLM(_DelegatingLLM(), self.tracer, cost_per_call=0.01)
        self.memory = Memory(self.llm)
        self.approval = ApprovalAgent(self.llm)
        self.orchestrator = Orchestrator()
        self._register_demo_tools()
        self._fail_once: set[str] = set()
        self.events = EventProcessor(
            handlers={
                "echo": lambda payload: payload,
                "ping": lambda payload: {"pong": True, "payload": payload},
                "fail_once": self._fail_once_handler,
            },
            sleep=lambda _seconds: None,
        )
        self.router = CostRouter(
            models={
                "haiku-sim": ModelConfig(client=self.llm, cost_per_call=0.002, max_complexity=20),
                "sonnet": ModelConfig(client=self.llm, cost_per_call=0.01, max_complexity=10_000),
            },
            budget=float(os.getenv("COST_BUDGET", "5.0")),
        )
        self.last_recall_ms: float | None = None

    def _fail_once_handler(self, payload: dict) -> dict:
        key = str(payload.get("id", "default"))
        if key not in self._fail_once:
            self._fail_once.add(key)
            raise RuntimeError("simulated transient failure")
        return {"recovered": True, "payload": payload}

    def _register_demo_tools(self) -> None:
        self.orchestrator.register(Tool(
            name="echo",
            fn=lambda text="": text,
            capabilities={"echo"},
            required_scope=None,
            priority=1,
        ))
        self.orchestrator.register(Tool(
            name="add",
            fn=lambda a=0, b=0: a + b,
            capabilities={"math"},
            required_scope=None,
            priority=1,
        ))
        self.orchestrator.register(Tool(
            name="wait",
            fn=lambda seconds=0.4: (time.sleep(float(seconds)), f"slept {seconds}s")[1],
            capabilities={"wait"},
            required_scope=None,
            priority=1,
        ))
        self.orchestrator.register(Tool(
            name="secret_note",
            fn=lambda text="": f"secured:{text}",
            capabilities={"secret"},
            required_scope="admin",
            priority=5,
        ))


runtime = AppRuntime()


def _builtin_react_tools() -> dict:
    return {
        "echo": lambda text="": text,
        "add": lambda a=0, b=0: a + b,
        "upper": lambda text="": str(text).upper(),
    }


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ErrorBody(BaseModel):
    error: str
    type: str
    detail: Any | None = None


class FieldSpec(BaseModel):
    name: str
    type: Literal["str", "int", "float", "bool"] = "str"


class StructuredRequest(BaseModel):
    text: str
    fields: list[FieldSpec] = Field(default_factory=lambda: [
        FieldSpec(name="name", type="str"),
        FieldSpec(name="age", type="int"),
    ])
    max_retries: int = 2


class StructuredResponse(BaseModel):
    data: dict[str, Any]
    failures: list[dict[str, Any]]


class ReactRequest(BaseModel):
    goal: str
    max_iterations: int = 5
    tools: list[str] = Field(default_factory=lambda: ["echo", "add", "upper"])


class ReactResponse(BaseModel):
    status: str
    answer: Any
    iterations: int
    trace: list[dict[str, Any]]


class OrchestratorRequest(BaseModel):
    capability: str
    scopes: list[str] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class OrchestratorParallelRequest(BaseModel):
    tasks: list[dict[str, Any]]
    scopes: list[str] = Field(default_factory=list)


class OrchestratorBenchmarkRequest(BaseModel):
    n: int = Field(default=3, ge=1, le=16)
    seconds: float = Field(default=0.4, ge=0.05, le=5.0)
    scopes: list[str] = Field(default_factory=list)


class MemoryTurnRequest(BaseModel):
    text: str


class MemoryRecallRequest(BaseModel):
    query: str
    k: int = 3


class MemoryStatsResponse(BaseModel):
    short_term_count: int
    long_term_count: int
    short_term: list[str]
    long_term: list[dict[str, Any]]
    last_recall_ms: float | None


class ApprovalHandleRequest(BaseModel):
    request: str


class ApprovalResumeRequest(BaseModel):
    ticket: str
    approved: bool
    human_note: str = ""


class CostRouterRequest(BaseModel):
    task: str


class EventProcessRequest(BaseModel):
    id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DebateRequest(BaseModel):
    question: str
    n_proposers: int = Field(default=3, ge=1, le=5)


class SelfEvalRequest(BaseModel):
    task: str
    criteria: str
    pass_threshold: float = 0.8
    max_attempts: int = 3


class AgentRunRequest(BaseModel):
    goal: str
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    force_model: str | None = None


class AgentResumeRequest(BaseModel):
    ticket: str
    approved: bool
    human_note: str = ""


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(
    title="Agentic",
    description="Live REST API over ten agent modules, traced via InstrumentedLLM.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_origin_regex=r"https://.*\.run\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_payload(exc: Exception, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorBody(
            error=str(exc),
            type=type(exc).__name__,
        ).model_dump(),
    )


def _unavailable(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"status": "unavailable", "mode": "real", "message": message},
    )


def llm_guard(work):
    """Run an LLM-backed body; provider errors become HTTP 200 + structured JSON."""
    try:
        return work()
    except AnthropicAuthenticationError:
        return _unavailable(AUTH_MESSAGE)
    except AnthropicRateLimitError:
        return _unavailable(RATE_MESSAGE)
    except AnthropicAPIError as exc:
        msg = getattr(exc, "message", None) or str(exc)
        return _unavailable(f"The model provider returned an error: {msg}")
    except LLMUnavailable:
        return _unavailable(AUTH_MESSAGE)


@app.exception_handler(LLMUnavailable)
async def llm_unavailable_handler(_request: Request, exc: LLMUnavailable):
    return _unavailable(AUTH_MESSAGE)


@app.exception_handler(AnthropicAuthenticationError)
async def anthropic_auth_handler(_request: Request, exc: AnthropicAuthenticationError):
    return _unavailable(AUTH_MESSAGE)


@app.exception_handler(AnthropicRateLimitError)
async def anthropic_rate_handler(_request: Request, exc: AnthropicRateLimitError):
    return _unavailable(RATE_MESSAGE)


@app.exception_handler(AnthropicAPIError)
async def anthropic_api_handler(_request: Request, exc: AnthropicAPIError):
    msg = getattr(exc, "message", None) or str(exc)
    return _unavailable(f"The model provider returned an error: {msg}")


@app.exception_handler(ExtractionError)
async def extraction_handler(_request: Request, exc: ExtractionError):
    return error_payload(exc, 422)


@app.exception_handler(PermissionDenied)
async def permission_handler(_request: Request, exc: PermissionDenied):
    return error_payload(exc, 403)


@app.exception_handler(UnknownTicket)
async def ticket_handler(_request: Request, exc: UnknownTicket):
    return error_payload(exc, 404)


@app.exception_handler(BudgetExceeded)
async def budget_handler(_request: Request, exc: BudgetExceeded):
    return error_payload(exc, 402)


@app.exception_handler(KeyError)
async def key_handler(_request: Request, exc: KeyError):
    return error_payload(exc, 404)


@app.exception_handler(json.JSONDecodeError)
async def json_handler(_request: Request, exc: json.JSONDecodeError):
    return error_payload(exc, 502)


@app.exception_handler(ValidationError)
async def pydantic_handler(_request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content=ErrorBody(error="validation failed", type="ValidationError", detail=exc.errors()).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=ErrorBody(error="request validation failed", type="RequestValidationError", detail=exc.errors()).model_dump(),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorBody(error=str(detail), type="HTTPException").model_dump(),
    )


@app.exception_handler(Exception)
async def generic_handler(_request: Request, exc: Exception):
    logger.exception("unhandled error")
    return error_payload(exc, 500)


@app.get("/health")
def health() -> dict[str, Any]:
    client, mode = get_llm()
    model = "fake-llm" if mode == "fake" else getattr(client, "name", "claude-sonnet-4-6")
    return {
        "ok": True,
        "model": model,
        "api_key_configured": mode == "real",
        "llm_mode": mode,
    }


@app.get("/config")
def config() -> dict[str, str]:
    client, mode = get_llm()
    model = "fake-llm" if mode == "fake" else getattr(client, "name", "claude-sonnet-4-6")
    return {"llm_mode": mode, "model": model}


@app.get("/docs-info")
def docs_info() -> dict[str, str]:
    return {"swagger": "/docs", "openapi": "/openapi.json"}


def _dynamic_schema(fields: list[FieldSpec]):
    defs: dict[str, Any] = {}
    for spec in fields:
        py_type = TYPE_MAP.get(spec.type, str)
        defs[spec.name] = (py_type, ...)
    return create_model("Extracted", **defs)


@app.post("/structured-output", response_model=None)
def structured_output(body: StructuredRequest):
    def work():
        schema = _dynamic_schema(body.fields)
        agent = StructuredAgent(runtime.llm, schema, max_retries=body.max_retries)
        result = agent.extract(body.text)
        return StructuredResponse(data=result.model_dump(), failures=agent.failures)

    return llm_guard(work)


@app.post("/react", response_model=None)
def react(body: ReactRequest):
    def work():
        available = _builtin_react_tools()
        unknown = [name for name in body.tools if name not in available]
        if unknown:
            raise HTTPException(status_code=400, detail={"error": f"unknown tools: {unknown}", "type": "ValueError"})
        tools = {name: available[name] for name in body.tools}
        agent = ReActAgent(runtime.llm, tools, max_iterations=body.max_iterations)
        result = agent.run(body.goal)
        return ReactResponse(
            status=result["status"],
            answer=result["answer"],
            iterations=result["iterations"],
            trace=agent.trace,
        )

    return llm_guard(work)


@app.post("/orchestrator")
def orchestrator(body: OrchestratorRequest) -> dict[str, Any]:
    result = runtime.orchestrator.execute(
        body.capability,
        set(body.scopes),
        **body.kwargs,
    )
    tool = runtime.orchestrator.resolve(body.capability)
    return {"ok": True, "tool": tool.name, "result": result}


@app.post("/orchestrator/parallel")
def orchestrator_parallel(body: OrchestratorParallelRequest) -> dict[str, Any]:
    results = runtime.orchestrator.execute_parallel(body.tasks, set(body.scopes))
    return {"results": results}


@app.post("/orchestrator/benchmark")
def orchestrator_benchmark(body: OrchestratorBenchmarkRequest) -> dict[str, Any]:
    """Measure real wall-clock sequential vs parallel execution of N wait tasks."""
    tasks = [
        {"capability": "wait", "kwargs": {"seconds": body.seconds}}
        for _ in range(body.n)
    ]
    scopes = set(body.scopes)

    start_seq = time.perf_counter()
    sequential = []
    for task in tasks:
        sequential.append({
            "ok": True,
            "result": runtime.orchestrator.execute(
                task["capability"], scopes, **task["kwargs"]
            ),
        })
    sequential_ms = (time.perf_counter() - start_seq) * 1000

    start_par = time.perf_counter()
    parallel = runtime.orchestrator.execute_parallel(tasks, scopes)
    parallel_ms = (time.perf_counter() - start_par) * 1000

    speedup = (sequential_ms / parallel_ms) if parallel_ms else 0.0
    return {
        "n": body.n,
        "seconds_per_task": body.seconds,
        "sequential_ms": sequential_ms,
        "parallel_ms": parallel_ms,
        "speedup": speedup,
        "sequential_results": sequential,
        "parallel_results": parallel,
    }


@app.post("/memory/turn")
def memory_turn(body: MemoryTurnRequest) -> dict[str, Any]:
    runtime.memory.add_turn(body.text)
    return {
        "short_term": list(runtime.memory.short_term),
        "long_term_count": len(runtime.memory.long_term),
    }


@app.post("/memory/recall")
def memory_recall(body: MemoryRecallRequest) -> dict[str, Any]:
    start = time.perf_counter()
    recalled = runtime.memory.recall(body.query, k=body.k)
    runtime.last_recall_ms = (time.perf_counter() - start) * 1000
    return {"recalled": recalled, "recall_ms": runtime.last_recall_ms}


@app.post("/memory/compress")
def memory_compress():
    def work():
        runtime.memory.compress()
        return {"long_term": runtime.memory.long_term}

    return llm_guard(work)


@app.get("/memory/stats", response_model=MemoryStatsResponse)
def memory_stats() -> MemoryStatsResponse:
    return MemoryStatsResponse(
        short_term_count=len(runtime.memory.short_term),
        long_term_count=len(runtime.memory.long_term),
        short_term=list(runtime.memory.short_term),
        long_term=list(runtime.memory.long_term),
        last_recall_ms=runtime.last_recall_ms,
    )


@app.post("/approval/handle")
def approval_handle(body: ApprovalHandleRequest):
    def work():
        prompt = (
            "Decide on this user request. Return JSON only with keys "
            'answer (string), confidence (0-1 float), action (string or null).\n'
            f"Request: {body.request}"
        )
        return runtime.approval.handle(prompt)

    return llm_guard(work)


@app.post("/approval/resume")
def approval_resume(body: ApprovalResumeRequest) -> dict[str, Any]:
    result = runtime.approval.resume(body.ticket, body.approved, body.human_note)
    result["audit"] = runtime.approval.audit_trail(body.ticket)
    return result


@app.post("/cost-router")
def cost_router_run(body: CostRouterRequest):
    def work():
        prompt = (
            "Complete the task. Return JSON only: "
            '{"answer": "...", "confidence": 0.0-1.0}\n'
            f"Task: {body.task}"
        )
        result = runtime.router.run_task(prompt)
        result["analytics"] = runtime.router.analytics()
        return result

    return llm_guard(work)


@app.get("/cost-router/analytics")
def cost_router_analytics() -> dict[str, Any]:
    return runtime.router.analytics()


@app.post("/events/process")
def events_process(body: EventProcessRequest) -> dict[str, Any]:
    return runtime.events.process(body.model_dump())


@app.post("/events/replay")
def events_replay() -> dict[str, Any]:
    recovered = runtime.events.replay_dead_letter()
    return {
        "recovered": recovered,
        "dead_letter": runtime.events.dead_letter,
        "processed_ids": list(runtime.events.processed.keys()),
    }


@app.post("/debate")
def debate(body: DebateRequest):
    def work():
        proposers = [runtime.llm] * body.n_proposers
        system = Debate(proposers=proposers, critic=runtime.llm, aggregator=runtime.llm)
        result = system.run(body.question)
        result["history"] = None
        return result

    return llm_guard(work)


@app.post("/self-eval")
def self_eval(body: SelfEvalRequest):
    def work():
        agent = SelfEvalAgent(
            worker=runtime.llm,
            judge=runtime.llm,
            pass_threshold=body.pass_threshold,
            max_attempts=body.max_attempts,
        )
        result = agent.run(body.task, body.criteria)
        result["history"] = agent.history
        return result

    return llm_guard(work)


@app.get("/observability/report")
def observability_report() -> dict[str, Any]:
    report = runtime.llm.report()
    report["spans"] = runtime.tracer.spans[-50:]
    return report


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _agent_sse_events(iterator):
    try:
        for ev in iterator:
            yield _sse(ev)
    except AnthropicAuthenticationError:
        yield _sse({"stage": "provider", "status": "unavailable", "message": AUTH_MESSAGE})
    except AnthropicRateLimitError:
        yield _sse({"stage": "provider", "status": "unavailable", "message": RATE_MESSAGE})
    except AnthropicAPIError as exc:
        msg = getattr(exc, "message", None) or str(exc)
        yield _sse({
            "stage": "provider",
            "status": "unavailable",
            "message": f"The model provider returned an error: {msg}",
        })
    except LLMUnavailable:
        yield _sse({"stage": "provider", "status": "unavailable", "message": AUTH_MESSAGE})
    except Exception as exc:
        yield _sse({"stage": "pipeline", "status": "error", "message": str(exc)})


@app.post("/agent/run")
async def agent_run(body: AgentRunRequest):
    pipeline = build_pipeline()
    pipeline._force_model = body.force_model

    def gen():
        yield from _agent_sse_events(pipeline.run_stream(body.goal, set(body.scopes)))

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/agent/resume")
async def agent_resume(body: AgentResumeRequest):
    pipeline = build_pipeline()

    def gen():
        yield from _agent_sse_events(
            pipeline.resume_stream(body.ticket, body.approved, body.human_note)
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/agent/config")
async def agent_config():
    client, mode = get_llm()
    if mode == "fake":
        model = "fake-llm"
    else:
        model = (
            os.getenv("ANTHROPIC_MODEL")
            or getattr(client, "model", None)
            or getattr(client, "name", None)
            or "claude-sonnet-4-6"
        )
    return {"llm_mode": mode, "model": model}
