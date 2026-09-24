"use client";

import { useCallback, useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import { InlineNotice } from "@/components/ui";

type AgentEvent = {
  stage?: string;
  status?: string;
  duration_ms?: number;
  payload?: Record<string, unknown>;
  iteration?: number;
  thought?: string | null;
  tool?: string | null;
  args?: Record<string, unknown> | null;
  observation?: string | null;
  ticket?: string;
  reason?: string;
  action?: string;
  answer?: string;
  total_cost?: number;
  total_time_ms?: number;
  stages?: number;
  model?: string;
  attempts?: number;
  message?: string;
  spans?: unknown[];
};

function icon(status?: string, stage?: string) {
  if (stage === "hitl_pause" || status === "pending") return "⏸";
  if (status === "error" || status === "unavailable") return "✗";
  if (status === "running") return "◐";
  return "✓";
}

function iconClass(status?: string, stage?: string) {
  if (stage === "hitl_pause" || status === "pending") return "text-amber-700";
  if (status === "error" || status === "unavailable") return "text-red-600";
  if (status === "running") return "text-sky-600 animate-pulse";
  return "text-emerald-700";
}

async function consumeSse(
  response: Response,
  onEvent: (ev: AgentEvent) => void,
) {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("no-stream");
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const json = line.replace(/^data:\s?/, "");
      try {
        onEvent(JSON.parse(json) as AgentEvent);
      } catch {
        /* skip malformed frame */
      }
    }
  }
}

export function AgentView() {
  const [goal, setGoal] = useState("");
  const [scopes, setScopes] = useState("read");
  const [forceModel, setForceModel] = useState("auto");
  const [advanced, setAdvanced] = useState(false);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"fake" | "real" | "unknown">("unknown");
  const [showTrace, setShowTrace] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const done = events.find((e) => e.stage === "done");
  const pause = [...events].reverse().find((e) => e.stage === "hitl_pause" && e.status === "pending");
  const terminal = events.some(
    (e) => e.stage === "done" || e.status === "error" || e.status === "unavailable",
  );
  const timeline = terminal
    ? events.map((e) => (e.status === "running" ? { ...e, status: "ok" } : e))
    : events;

  useEffect(() => {
    void fetch(`${API_URL}/agent/config`)
      .then((r) => r.json())
      .then((d) => {
        if (d.llm_mode === "fake" || d.llm_mode === "real") setMode(d.llm_mode);
      })
      .catch(() => undefined);
  }, []);

  const run = useCallback(async () => {
    setEvents([]);
    setNotice(undefined);
    setShowRaw(false);
    setShowTrace(false);
    setRunning(true);
    try {
      const response = await fetch(`${API_URL}/agent/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal,
          scopes: scopes.split(",").map((s) => s.trim()).filter(Boolean),
          force_model: forceModel === "auto" ? null : forceModel,
        }),
      });
      if (!response.body) {
        setNotice("Couldn't reach the server. Retrying...");
        return;
      }
      await consumeSse(response, (ev) => {
        if (ev.status === "unavailable") setNotice(ev.message);
        setEvents((prev) => [...prev, ev]);
      });
    } catch {
      setNotice("Couldn't reach the server. Retrying...");
    } finally {
      setRunning(false);
    }
  }, [forceModel, goal, scopes]);

  const resume = useCallback(
    async (approved: boolean) => {
      if (!pause?.ticket) return;
      setRunning(true);
      try {
        const response = await fetch(`${API_URL}/agent/resume`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ticket: pause.ticket,
            approved,
            human_note: note,
          }),
        });
        await consumeSse(response, (ev) => {
          if (ev.status === "unavailable") setNotice(ev.message);
          setEvents((prev) => [...prev, ev]);
        });
      } catch {
        setNotice("Couldn't reach the server. Retrying...");
      } finally {
        setRunning(false);
      }
    },
    [note, pause],
  );

  return (
    <div className="space-y-10">
      <div className="flex items-start justify-between gap-4">
        <div className="max-w-2xl space-y-3">
          <p className="text-xs uppercase tracking-[0.18em] text-peach-500">Agent</p>
          <h1 className="text-4xl font-medium tracking-tight">One goal. Ten patterns. One trace.</h1>
          <p className="text-peach-800/70">State a goal. The agent decides which patterns to use.</p>
        </div>
        <span
          title={
            mode === "real"
              ? "Connected to the live model."
              : "Scripted model. No API key required."
          }
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            mode === "real" ? "bg-emerald-100 text-emerald-800" : "bg-stone-200 text-stone-600"
          }`}
        >
          {mode === "real" ? "Live model" : "Demo mode"}
        </span>
      </div>

      <div className="space-y-4 rounded-2xl border border-peach-200 bg-white p-6">
        <textarea
          rows={4}
          className="w-full rounded-lg border border-peach-300 bg-peach-50 px-3 py-2 text-sm text-peach-900 outline-none focus:ring-2 focus:ring-peach-400/40"
          placeholder="State a goal. The agent will figure out which tools to use."
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
        />
        <button
          type="button"
          disabled={running || !goal.trim()}
          onClick={() => void run()}
          className="rounded-lg bg-peach-400 px-4 py-2 text-sm font-medium text-peach-900 hover:bg-peach-300 disabled:opacity-50"
        >
          {running ? "Running…" : "Run Agent"}
        </button>
        <button
          type="button"
          className="ml-4 text-xs underline underline-offset-2 text-peach-800/70"
          onClick={() => setAdvanced((v) => !v)}
        >
          {advanced ? "Hide advanced" : "Advanced"}
        </button>
        {advanced ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="text-xs uppercase tracking-[0.14em] text-peach-800/60">Force model</span>
              <select
                className="w-full rounded-lg border border-peach-300 bg-white px-3 py-2"
                value={forceModel}
                onChange={(e) => setForceModel(e.target.value)}
              >
                <option value="auto">Auto</option>
                <option value="small">small</option>
                <option value="medium">medium</option>
                <option value="large">large</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs uppercase tracking-[0.14em] text-peach-800/60">Scopes</span>
              <select
                className="w-full rounded-lg border border-peach-300 bg-white px-3 py-2"
                value={scopes}
                onChange={(e) => setScopes(e.target.value)}
              >
                <option value="read">read</option>
                <option value="read,write">write</option>
                <option value="read,write,admin">admin</option>
              </select>
            </label>
          </div>
        ) : null}
      </div>

      {notice ? <InlineNotice tone="info">{notice}</InlineNotice> : null}

      <section className="space-y-3">
        <h2 className="text-lg">Timeline</h2>
        {events.length === 0 && !running ? (
          <p className="text-sm text-peach-800/60">
            No run yet. Enter a goal and press Run Agent to stream stages live.
          </p>
        ) : null}
        <ol className="space-y-2">
          {timeline.map((ev, i) => (
            <li key={`${ev.stage}-${i}`} className="rounded-xl border border-peach-200 bg-white">
              <button
                type="button"
                className="flex w-full items-center justify-between px-4 py-3 text-left"
                onClick={() => setOpen((s) => ({ ...s, [i]: !s[i] }))}
              >
                <span className="flex items-center gap-3 font-mono text-sm">
                  <span className={iconClass(ev.status, ev.stage)}>{icon(ev.status, ev.stage)}</span>
                  {ev.stage}
                </span>
                <span className="font-mono text-xs text-peach-800/60">
                  {typeof ev.duration_ms === "number" ? `${ev.duration_ms.toFixed(3)} ms` : ""}
                  {ev.payload && typeof ev.payload.model === "string" ? ` → model: ${ev.payload.model}` : ""}
                  {ev.stage === "hitl_pause" && ev.ticket ? ` ticket: ${ev.ticket}` : ""}
                </span>
              </button>
              {open[i] ? (
                <div className="space-y-1 border-t border-peach-100 px-4 py-3 text-sm text-peach-800">
                  {ev.status ? <p>Status: {ev.status}</p> : null}
                  {typeof ev.iteration === "number" ? <p>Iteration: {ev.iteration}</p> : null}
                  {ev.thought ? <p>Thought: {ev.thought}</p> : null}
                  {ev.tool ? <p>Tool: {ev.tool}</p> : null}
                  {ev.args ? (
                    <p>
                      Args: {Object.entries(ev.args).map(([k, v]) => `${k}=${String(v)}`).join(", ") || "none"}
                    </p>
                  ) : null}
                  {ev.observation ? <p>Observation: {ev.observation}</p> : null}
                  {ev.payload && Array.isArray(ev.payload.recalled) ? (
                    <p>
                      Recalled: {ev.payload.recalled.length === 0 ? "none" : ev.payload.recalled.map(String).join(" · ")}
                    </p>
                  ) : null}
                  {typeof ev.payload?.cost_per_call === "number" ? (
                    <p>Cost per call: ${Number(ev.payload.cost_per_call).toFixed(3)}</p>
                  ) : null}
                  {ev.message ? <p>Message: {ev.message}</p> : null}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </section>

      {pause && !done ? (
        <section className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50 p-6">
          <h2 className="text-lg">Human approval</h2>
          <p>Action: {pause.action || "n/a"}</p>
          <p>Reason: {pause.reason || "n/a"}</p>
          <p className="font-mono text-sm">Ticket: {pause.ticket}</p>
          <label className="block space-y-1 text-sm">
            Note
            <input
              className="w-full rounded-lg border border-peach-300 bg-white px-3 py-2"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="flex gap-3">
            <button type="button" className="rounded-lg bg-peach-400 px-4 py-2 text-sm" onClick={() => void resume(true)}>
              Approve
            </button>
            <button type="button" className="rounded-lg bg-stone-200 px-4 py-2 text-sm" onClick={() => void resume(false)}>
              Reject
            </button>
          </div>
        </section>
      ) : null}

      {done ? (
        <section className="space-y-3 rounded-2xl border border-peach-200 bg-white p-6">
          <h2 className="text-lg">Summary</h2>
          <p>Answer {done.answer}</p>
          <p>Total cost ${Number(done.total_cost ?? 0).toFixed(3)}</p>
          <p>Total time {(Number(done.total_time_ms ?? 0) / 1000).toFixed(3)} s</p>
          <p>Stages {done.stages}</p>
          <p>Model {done.model}</p>
          <p>Attempts {done.attempts}</p>
          <button type="button" className="block text-sm underline" onClick={() => setShowTrace((v) => !v)}>
            {showTrace ? "Hide full trace" : "Show full trace"}
          </button>
          {showTrace && Array.isArray(done.spans) ? (
            <ul className="font-mono text-xs">
              {done.spans.map((span, i) => {
                const s = span as { name?: string; duration?: number };
                return (
                  <li key={i}>
                    {s.name} {Number(s.duration ?? 0).toFixed(3)} s
                  </li>
                );
              })}
            </ul>
          ) : null}
          <button type="button" className="block text-sm underline" onClick={() => setShowRaw((v) => !v)}>
            {showRaw ? "Hide raw JSON" : "Show raw JSON"}
          </button>
          {showRaw ? (
            <pre className="overflow-auto font-mono text-xs">{JSON.stringify(events, null, 2)}</pre>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
