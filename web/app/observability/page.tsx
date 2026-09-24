"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { JsonBlock, Spinner } from "@/components/ui";

type Report = {
  calls: number;
  total_cost: number;
  avg_latency: number;
  alerts: Array<{ type: string; prompt: string; count: number }>;
  spans?: unknown[];
};

export default function ObservabilityPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<Report>("/observability/report");
      setReport(data);
      setError(undefined);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 4000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="space-y-10">
      <div className="space-y-2">
        <p className="text-xs uppercase tracking-[0.18em] text-peach-500">GET /observability/report</p>
        <h1 className="text-3xl font-medium tracking-tight">Observability</h1>
        <p className="text-sm text-peach-800/70">Live InstrumentedLLM accounting. Refreshes every 4s.</p>
      </div>
      {loading && !report ? (
        <div className="flex items-center gap-2 text-sm text-peach-800/60">
          <Spinner /> Loading report
        </div>
      ) : null}
      {error ? <JsonBlock value={error} /> : null}
      {report ? (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Total calls" value={String(report.calls)} />
            <Stat label="Total cost" value={report.total_cost.toFixed(4)} />
            <Stat label="Avg latency (s)" value={report.avg_latency.toFixed(4)} />
          </div>
          <div className="space-y-3">
            <h2 className="text-sm uppercase tracking-[0.14em] text-peach-800/60">Loop-alert feed</h2>
            {report.alerts.length === 0 ? (
              <p className="text-sm text-peach-800/60">No loop alerts from the live tracer.</p>
            ) : (
              <ul className="space-y-3">
                {report.alerts.map((alert, i) => (
                  <li key={`${alert.count}-${i}`} className="rounded-xl border border-peach-200 bg-white p-4 font-mono text-sm">
                    <span className="text-peach-500">{alert.type}</span>
                    {" · count "}
                    {alert.count}
                    <p className="mt-2 whitespace-pre-wrap text-peach-800/70">{alert.prompt}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <JsonBlock value={report} />
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-peach-200 bg-white p-5">
      <p className="text-xs uppercase tracking-[0.14em] text-peach-800/60">{label}</p>
      <p className="mt-3 font-mono text-3xl">{value}</p>
    </div>
  );
}
