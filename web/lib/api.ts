export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.body = body;
  }
}

export async function api<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  const text = await response.text();
  let parsed: unknown = text;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = { error: text, type: "NonJSON" };
  }
  if (!response.ok) {
    throw new ApiError(response.status, parsed);
  }
  return parsed as T;
}

export type ModuleCard = {
  slug: string;
  title: string;
  description: string;
  href: string;
};

export const MODULES: ModuleCard[] = [
  {
    slug: "structured-output",
    title: "Structured Output",
    description: "Schema-validated extraction with retry on parse failures.",
    href: "/playground/structured-output",
  },
  {
    slug: "react",
    title: "ReAct Loop",
    description: "Bounded think-act-observe loop with graceful degradation.",
    href: "/playground/react",
  },
  {
    slug: "orchestrator",
    title: "Tool Orchestrator",
    description: "Capability routing, scopes, and parallel tool execution.",
    href: "/playground/orchestrator",
  },
  {
    slug: "memory",
    title: "Memory Agent",
    description: "Short-term buffer, long-term recall, and LLM compression.",
    href: "/playground/memory",
  },
  {
    slug: "approval",
    title: "HITL Approval",
    description: "Pause on uncertainty or protected actions, then resume.",
    href: "/playground/approval",
  },
  {
    slug: "cost-router",
    title: "Cost Router",
    description: "Budget-bound routing with at-most-once escalation.",
    href: "/playground/cost-router",
  },
  {
    slug: "events",
    title: "Event Automation",
    description: "Idempotent processing, retries, and a dead-letter queue.",
    href: "/playground/events",
  },
  {
    slug: "debate",
    title: "Debate System",
    description: "Proposers, critic scoring, and aggregator synthesis.",
    href: "/playground/debate",
  },
  {
    slug: "self-eval",
    title: "Self-Eval",
    description: "Generate, judge, refine, and keep the best attempt.",
    href: "/playground/self-eval",
  },
  {
    slug: "observability",
    title: "Observability",
    description: "Live call counts, cost, latency, and loop-alert feed.",
    href: "/observability",
  },
];
