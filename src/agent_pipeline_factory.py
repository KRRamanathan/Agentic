"""Wire existing modules into an AgentPipeline."""
from __future__ import annotations

from cost_router import CostRouter, ModelConfig
from debate_system import Debate
from hitl_approval import ApprovalAgent
from memory_agent import Memory
from observability import InstrumentedLLM, Tracer
from self_eval import SelfEvalAgent
from src.agent_pipeline import AgentPipeline, ExtractSchema
from src.llm_factory import get_llm
from structured_output import StructuredAgent


class _DelegatingLLM:
    def complete(self, prompt: str) -> str:
        client, _mode = get_llm()
        return client.complete(prompt)


def build_pipeline() -> AgentPipeline:
    """Wire get_llm() + Tracer + Memory + CostRouter + ApprovalAgent + tools."""
    tracer = Tracer()
    llm = InstrumentedLLM(_DelegatingLLM(), tracer, cost_per_call=0.01)
    memory = Memory(llm)
    router = CostRouter(
        models={
            "haiku-sim": ModelConfig(client=llm, cost_per_call=0.002, max_complexity=20),
            "sonnet": ModelConfig(client=llm, cost_per_call=0.01, max_complexity=10_000),
        },
        budget=5.0,
    )
    hitl = ApprovalAgent(llm)

    def extract(text: str = "", source: str = "", **kwargs) -> dict:
        payload = text or source or str(kwargs)
        agent = StructuredAgent(llm, ExtractSchema, max_retries=1)
        return agent.extract(str(payload)).model_dump()

    def debate(question: str = "", **kwargs) -> dict:
        q = question or str(kwargs.get("goal") or kwargs)
        system = Debate(proposers=[llm, llm, llm], critic=llm, aggregator=llm)
        return system.run(str(q))

    def self_eval(task: str = "", criteria: str = "", **kwargs) -> dict:
        t = task or str(kwargs.get("goal") or kwargs)
        c = criteria or "Accurate, concise, and complete."
        agent = SelfEvalAgent(worker=llm, judge=llm, pass_threshold=0.8, max_attempts=2)
        return agent.run(str(t), str(c))

    tools = {
        "extract": extract,
        "debate": debate,
        "self_eval": self_eval,
    }
    return AgentPipeline(
        llm=llm,
        tracer=tracer,
        memory=memory,
        router=router,
        hitl=hitl,
        tools=tools,
    )
