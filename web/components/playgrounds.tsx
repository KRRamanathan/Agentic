"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { Button, Field, ResultPane, inputClass } from "@/components/ui";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function useLiveCall() {
  const [data, setData] = useState<unknown>();
  const [notice, setNotice] = useState<string>();
  const [retrying, setRetrying] = useState(false);
  const [loading, setLoading] = useState(false);

  async function run<T>(fn: () => Promise<T>) {
    setLoading(true);
    setNotice(undefined);
    setRetrying(false);
    try {
      const result = await fn();
      setData(result);
      return result;
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      const retryable = !(err instanceof ApiError) || status >= 500;
      if (retryable) {
        setRetrying(true);
        await sleep(2000);
        try {
          const result = await fn();
          setRetrying(false);
          setData(result);
          return result;
        } catch {
          setRetrying(false);
          setNotice("Couldn't reach the server. Retrying...");
          setData(undefined);
          return undefined;
        }
      }
      setNotice("Couldn't complete that request.");
      setData(undefined);
      return undefined;
    } finally {
      setLoading(false);
    }
  }

  return { data, notice, retrying, loading, run, setData };
}

function Frame({
  title,
  hint,
  children,
  data,
  notice,
  retrying,
}: {
  title: string;
  hint: string;
  children: ReactNode;
  data: unknown;
  notice?: string;
  retrying?: boolean;
}) {
  return (
    <div className="grid gap-10 lg:grid-cols-2">
      <div className="space-y-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-medium tracking-tight">{title}</h1>
          <p className="text-sm text-peach-800/70">{hint}</p>
        </div>
        {children}
      </div>
      <div className="space-y-3">
        <p className="text-xs uppercase tracking-[0.14em] text-peach-800/60">Live output</p>
        <ResultPane data={data} notice={notice} retrying={retrying} />
      </div>
    </div>
  );
}

export function StructuredPlayground() {
  const live = useLiveCall();
  const [text, setText] = useState("Ada Lovelace was 36 years old.");
  const [fields, setFields] = useState("name:str\nage:int");

  return (
    <Frame title="Structured Output" hint="POST /structured-output" data={live.data} notice={live.notice} retrying={live.retrying}>
      <Field label="Source text">
        <textarea className={`${inputClass} min-h-28`} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <Field label="Fields (name:type per line)">
        <textarea className={`${inputClass} min-h-24 font-mono`} value={fields} onChange={(e) => setFields(e.target.value)} />
      </Field>
      <Button
        loading={live.loading}
        onClick={() =>
          live.run(() =>
            api("/structured-output", {
              method: "POST",
              body: JSON.stringify({
                text,
                fields: fields
                  .split("\n")
                  .map((line) => line.trim())
                  .filter(Boolean)
                  .map((line) => {
                    const [name, type] = line.split(":");
                    return { name: name.trim(), type: (type || "str").trim() };
                  }),
              }),
            }),
          )
        }
      >
        Extract
      </Button>
    </Frame>
  );
}

export function ReactPlayground() {
  const live = useLiveCall();
  const [goal, setGoal] = useState("Add 2 and 3, then uppercase the word agentic.");
  return (
    <Frame title="ReAct Loop" hint="POST /react" data={live.data} notice={live.notice} retrying={live.retrying}>
      <Field label="Goal">
        <textarea className={`${inputClass} min-h-28`} value={goal} onChange={(e) => setGoal(e.target.value)} />
      </Field>
      <Button
        loading={live.loading}
        onClick={() =>
          live.run(() =>
            api("/react", {
              method: "POST",
              body: JSON.stringify({ goal, tools: ["echo", "add", "upper"] }),
            }),
          )
        }
      >
        Run loop
      </Button>
    </Frame>
  );
}

export function OrchestratorPlayground() {
  const live = useLiveCall();
  const [capability, setCapability] = useState("echo");
  const [scopes, setScopes] = useState("public");
  const [kwargs, setKwargs] = useState('{"text":"hello"}');
  return (
    <Frame
      title="Tool Orchestrator"
      hint="POST /orchestrator and /orchestrator/parallel"
      data={live.data}
      notice={live.notice} retrying={live.retrying}
    >
      <Field label="Capability">
        <input className={inputClass} value={capability} onChange={(e) => setCapability(e.target.value)} />
      </Field>
      <Field label="Scopes (comma-separated)">
        <input className={inputClass} value={scopes} onChange={(e) => setScopes(e.target.value)} />
      </Field>
      <Field label="kwargs JSON">
        <textarea className={`${inputClass} min-h-24 font-mono`} value={kwargs} onChange={(e) => setKwargs(e.target.value)} />
      </Field>
      <div className="flex flex-wrap gap-3">
        <Button
          loading={live.loading}
          onClick={() =>
            live.run(() =>
              api("/orchestrator", {
                method: "POST",
                body: JSON.stringify({
                  capability,
                  scopes: scopes.split(",").map((s) => s.trim()).filter(Boolean),
                  kwargs: JSON.parse(kwargs || "{}"),
                }),
              }),
            )
          }
        >
          Execute
        </Button>
        <Button
          loading={live.loading}
          className="bg-peach-200"
          onClick={() =>
            live.run(() =>
              api("/orchestrator/parallel", {
                method: "POST",
                body: JSON.stringify({
                  scopes: scopes.split(",").map((s) => s.trim()).filter(Boolean),
                  tasks: [
                    { capability: "echo", kwargs: { text: "a" } },
                    { capability: "math", kwargs: { a: 2, b: 3 } },
                    { capability: "wait", kwargs: { seconds: 0.2 } },
                  ],
                }),
              }),
            )
          }
        >
          Run parallel demo
        </Button>
      </div>
    </Frame>
  );
}

export function MemoryPlayground() {
  const live = useLiveCall();
  const [text, setText] = useState("The project deadline is Friday.");
  const [query, setQuery] = useState("deadline");
  return (
    <Frame title="Memory Agent" hint="POST /memory/turn, /recall, /compress · GET /memory/stats" data={live.data} notice={live.notice} retrying={live.retrying}>
      <Field label="Turn">
        <input className={inputClass} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <Field label="Recall query">
        <input className={inputClass} value={query} onChange={(e) => setQuery(e.target.value)} />
      </Field>
      <div className="flex flex-wrap gap-3">
        <Button loading={live.loading} onClick={() => live.run(() => api("/memory/turn", { method: "POST", body: JSON.stringify({ text }) }))}>
          Add turn
        </Button>
        <Button loading={live.loading} onClick={() => live.run(() => api("/memory/recall", { method: "POST", body: JSON.stringify({ query, k: 3 }) }))}>
          Recall
        </Button>
        <Button loading={live.loading} onClick={() => live.run(() => api("/memory/compress", { method: "POST" }))}>
          Compress
        </Button>
        <Button loading={live.loading} className="bg-peach-200" onClick={() => live.run(() => api("/memory/stats"))}>
          Stats
        </Button>
      </div>
    </Frame>
  );
}

export function ApprovalPlayground() {
  const live = useLiveCall();
  const [request, setRequest] = useState("Refund order #1842 for $50.");
  const [ticket, setTicket] = useState("");
  return (
    <Frame title="HITL Approval" hint="POST /approval/handle and /approval/resume" data={live.data} notice={live.notice} retrying={live.retrying}>
      <Field label="Request">
        <textarea className={`${inputClass} min-h-24`} value={request} onChange={(e) => setRequest(e.target.value)} />
      </Field>
      <Button
        loading={live.loading}
        onClick={async () => {
          const result = await live.run<{ ticket?: string }>(() =>
            api("/approval/handle", { method: "POST", body: JSON.stringify({ request }) }),
          );
          if (result?.ticket) setTicket(result.ticket);
        }}
      >
        Handle
      </Button>
      <Field label="Ticket">
        <input className={inputClass} value={ticket} onChange={(e) => setTicket(e.target.value)} />
      </Field>
      <div className="flex gap-3">
        <Button
          loading={live.loading}
          onClick={() =>
            live.run(() =>
              api("/approval/resume", {
                method: "POST",
                body: JSON.stringify({ ticket, approved: true, human_note: "ok" }),
              }),
            )
          }
        >
          Approve
        </Button>
        <Button
          loading={live.loading}
          className="bg-peach-200"
          onClick={() =>
            live.run(() =>
              api("/approval/resume", {
                method: "POST",
                body: JSON.stringify({ ticket, approved: false, human_note: "rejected" }),
              }),
            )
          }
        >
          Abort
        </Button>
      </div>
    </Frame>
  );
}

export function CostRouterPlayground() {
  const live = useLiveCall();
  const [task, setTask] = useState("Summarize this sentence: agents should stay cheap.");
  return (
    <Frame title="Cost Router" hint="POST /cost-router · GET /cost-router/analytics" data={live.data} notice={live.notice} retrying={live.retrying}>
      <Field label="Task">
        <textarea className={`${inputClass} min-h-28`} value={task} onChange={(e) => setTask(e.target.value)} />
      </Field>
      <div className="flex gap-3">
        <Button loading={live.loading} onClick={() => live.run(() => api("/cost-router", { method: "POST", body: JSON.stringify({ task }) }))}>
          Route task
        </Button>
        <Button loading={live.loading} className="bg-peach-200" onClick={() => live.run(() => api("/cost-router/analytics"))}>
          Analytics
        </Button>
      </div>
    </Frame>
  );
}

export function EventsPlayground() {
  const live = useLiveCall();
  const [id, setId] = useState("evt-1");
  const [type, setType] = useState("echo");
  const [payload, setPayload] = useState('{"hello":true}');
  return (
    <Frame title="Event Automation" hint="POST /events/process and /events/replay · types: echo, ping, fail_once" data={live.data} notice={live.notice} retrying={live.retrying}>
      <Field label="Event id">
        <input className={inputClass} value={id} onChange={(e) => setId(e.target.value)} />
      </Field>
      <Field label="Type">
        <input className={inputClass} value={type} onChange={(e) => setType(e.target.value)} />
      </Field>
      <Field label="Payload JSON">
        <textarea className={`${inputClass} min-h-24 font-mono`} value={payload} onChange={(e) => setPayload(e.target.value)} />
      </Field>
      <div className="flex gap-3">
        <Button
          loading={live.loading}
          onClick={() =>
            live.run(() =>
              api("/events/process", {
                method: "POST",
                body: JSON.stringify({ id, type, payload: JSON.parse(payload || "{}") }),
              }),
            )
          }
        >
          Process
        </Button>
        <Button loading={live.loading} className="bg-peach-200" onClick={() => live.run(() => api("/events/replay", { method: "POST" }))}>
          Replay DLQ
        </Button>
      </div>
    </Frame>
  );
}

export function DebatePlayground() {
  const live = useLiveCall();
  const [question, setQuestion] = useState("Should we use a cheaper model for simple extraction?");
  return (
    <Frame title="Debate System" hint="POST /debate" data={live.data} notice={live.notice} retrying={live.retrying}>
      <Field label="Question">
        <textarea className={`${inputClass} min-h-28`} value={question} onChange={(e) => setQuestion(e.target.value)} />
      </Field>
      <Button loading={live.loading} onClick={() => live.run(() => api("/debate", { method: "POST", body: JSON.stringify({ question, n_proposers: 3 }) }))}>
        Debate
      </Button>
    </Frame>
  );
}

export function SelfEvalPlayground() {
  const live = useLiveCall();
  const [task, setTask] = useState("Write a one-sentence definition of idempotency.");
  const [criteria, setCriteria] = useState("Accurate, concise, no jargon pile-up.");
  return (
    <Frame title="Self-Eval" hint="POST /self-eval" data={live.data} notice={live.notice} retrying={live.retrying}>
      <Field label="Task">
        <textarea className={`${inputClass} min-h-24`} value={task} onChange={(e) => setTask(e.target.value)} />
      </Field>
      <Field label="Criteria">
        <textarea className={`${inputClass} min-h-24`} value={criteria} onChange={(e) => setCriteria(e.target.value)} />
      </Field>
      <Button
        loading={live.loading}
        onClick={() =>
          live.run(() =>
            api("/self-eval", {
              method: "POST",
              body: JSON.stringify({ task, criteria }),
            }),
          )
        }
      >
        Evaluate
      </Button>
    </Frame>
  );
}
