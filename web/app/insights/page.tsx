"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button, Field, InlineNotice, JsonBlock, inputClass } from "@/components/ui";

type Analytics = {
  total_cost: number;
  calls: number;
  by_model: Record<string, number>;
  escalation_rate: number;
};

type MemoryStats = {
  short_term_count: number;
  long_term_count: number;
  short_term: string[];
  long_term: unknown[];
  last_recall_ms: number | null;
};

type Benchmark = {
  n: number;
  seconds_per_task: number;
  sequential_ms: number;
  parallel_ms: number;
  speedup: number;
};

export default function InsightsPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [memory, setMemory] = useState<MemoryStats | null>(null);
  const [bench, setBench] = useState<Benchmark | null>(null);
  const [error, setError] = useState<string>();
  const [n, setN] = useState(5);
  const [seconds, setSeconds] = useState(0.2);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, m] = await Promise.all([
        api<Analytics>("/cost-router/analytics"),
        api<MemoryStats>("/memory/stats"),
      ]);
      setAnalytics(a);
      setMemory(m);
      setError(undefined);
    } catch (err) {
      setError("Couldn't reach the server. Retrying...");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function runBenchmark() {
    setRunning(true);
    try {
      const result = await api<Benchmark>("/orchestrator/benchmark", {
        method: "POST",
        body: JSON.stringify({ n, seconds }),
      });
      setBench(result);
      setError(undefined);
    } catch (err) {
      setError("Couldn't reach the server. Retrying...");
    } finally {
      setRunning(false);
    }
  }

  const maxSpend = analytics
    ? Math.max(0, ...Object.values(analytics.by_model))
    : 0;

  return (
    <div className="space-y-12">
      <div className="space-y-2">
        <p className="text-xs uppercase tracking-[0.18em] text-peach-500">Live backend numbers</p>
        <h1 className="text-3xl font-medium tracking-tight">Cost & Memory</h1>
        <p className="text-sm text-peach-800/70">
          Charts and counts come from /cost-router/analytics, /memory/stats, and /orchestrator/benchmark.
        </p>
      </div>

      {error ? <InlineNotice tone="info">{error}</InlineNotice> : null}

      <section className="space-y-5">
        <h2 className="text-lg">Cost router</h2>
        {analytics ? (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Stat label="Calls" value={String(analytics.calls)} />
              <Stat label="Total spend" value={analytics.total_cost.toFixed(4)} />
              <Stat label="Escalation rate" value={analytics.escalation_rate.toFixed(4)} />
            </div>
            <div className="rounded-2xl border border-peach-200 bg-white p-6">
              <p className="mb-6 text-xs uppercase tracking-[0.14em] text-peach-800/60">Spend by model</p>
              {Object.keys(analytics.by_model).length === 0 ? (
                <p className="text-sm text-peach-800/60">No ledger entries yet. Run a cost-router task.</p>
              ) : (
                <div className="space-y-4">
                  {Object.entries(analytics.by_model).map(([model, spend]) => (
                    <div key={model} className="space-y-2">
                      <div className="flex justify-between font-mono text-sm">
                        <span>{model}</span>
                        <span>{spend.toFixed(4)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-peach-200">
                        <div
                          className="h-2 rounded-full bg-peach-400"
                          style={{ width: maxSpend ? `${(spend / maxSpend) * 100}%` : "0%" }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <p className="text-sm text-peach-800/60">Loading analytics…</p>
        )}
      </section>

      <section className="space-y-5">
        <h2 className="text-lg">Memory</h2>
        {memory ? (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Stat label="Short-term count" value={String(memory.short_term_count)} />
              <Stat label="Long-term count" value={String(memory.long_term_count)} />
              <Stat
                label="Last recall latency"
                value={memory.last_recall_ms === null ? "n/a" : `${memory.last_recall_ms.toFixed(3)} ms`}
              />
            </div>
            <JsonBlock value={memory} />
          </>
        ) : (
          <p className="text-sm text-peach-800/60">Loading memory stats…</p>
        )}
      </section>

      <section className="space-y-5">
        <h2 className="text-lg">Orchestrator speedup</h2>
        <p className="text-sm text-peach-800/70">
          This runs N wait tasks sequentially, then the same N in parallel, and reports wall-clock ms from the backend.
        </p>
        <div className="flex flex-wrap items-end gap-4">
          <Field label="N tasks">
            <input
              className={inputClass}
              type="number"
              min={1}
              max={16}
              value={n}
              onChange={(e) => setN(Number(e.target.value))}
            />
          </Field>
          <Field label="Seconds per wait">
            <input
              className={inputClass}
              type="number"
              step="0.05"
              min={0.05}
              max={5}
              value={seconds}
              onChange={(e) => setSeconds(Number(e.target.value))}
            />
          </Field>
          <Button loading={running} onClick={() => void runBenchmark()}>
            Measure
          </Button>
        </div>
        {bench ? (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Stat label="Sequential ms" value={bench.sequential_ms.toFixed(1)} />
              <Stat label="Parallel ms" value={bench.parallel_ms.toFixed(1)} />
              <Stat label="Speedup" value={`${bench.speedup.toFixed(2)}×`} />
            </div>
            <div className="flex h-40 items-end gap-6 rounded-2xl border border-peach-200 bg-white p-6">
              <Bar label="seq" value={bench.sequential_ms} max={Math.max(bench.sequential_ms, bench.parallel_ms)} />
              <Bar label="par" value={bench.parallel_ms} max={Math.max(bench.sequential_ms, bench.parallel_ms)} />
            </div>
            <JsonBlock value={bench} />
          </>
        ) : (
          <p className="text-sm text-peach-800/60">No measurement yet. Press Measure to run the live benchmark.</p>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-peach-200 bg-white p-5">
      <p className="text-xs uppercase tracking-[0.14em] text-peach-800/60">{label}</p>
      <p className="mt-3 font-mono text-2xl">{value}</p>
    </div>
  );
}

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  const height = max ? Math.max(8, (value / max) * 100) : 8;
  return (
    <div className="flex h-full flex-1 flex-col justify-end gap-2">
      <div className="rounded-t-md bg-peach-400" style={{ height: `${height}%` }} />
      <p className="font-mono text-xs text-peach-800/60">{label}</p>
    </div>
  );
}
