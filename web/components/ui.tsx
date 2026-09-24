"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useState } from "react";

export function InlineNotice({
  tone = "info",
  children,
  details,
}: {
  tone?: "info" | "warn" | "success";
  children: ReactNode;
  details?: string;
}) {
  const [open, setOpen] = useState(false);
  const tones = {
    info: "border-stone-200 bg-stone-50 text-stone-700",
    warn: "border-amber-200 bg-amber-50 text-amber-900",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
  };
  return (
    <div className={`rounded-xl border px-4 py-3 text-sm ${tones[tone]}`}>
      <p>{children}</p>
      {details ? (
        <div className="mt-2">
          <button
            type="button"
            className="text-xs underline underline-offset-2"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Hide details" : "Details"}
          </button>
          {open ? (
            <pre className="mt-2 overflow-auto font-mono text-xs opacity-80">{details}</pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function isUnavailable(
  value: unknown,
): value is { status: "unavailable"; message: string; mode?: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    (value as { status: string }).status === "unavailable" &&
    typeof (value as { message?: unknown }).message === "string"
  );
}

export function ResultPane({
  data,
  notice,
  retrying,
}: {
  data: unknown;
  notice?: string;
  retrying?: boolean;
}) {
  if (retrying) {
    return (
      <InlineNotice tone="info">Couldn't reach the server. Retrying...</InlineNotice>
    );
  }
  if (notice) {
    return <InlineNotice tone="info">{notice}</InlineNotice>;
  }
  if (isUnavailable(data)) {
    return <InlineNotice tone="info">{data.message}</InlineNotice>;
  }
  return <JsonBlock value={data} />;
}

export function JsonBlock({ value }: { value: unknown }) {
  if (value === undefined) {
    return (
      <p className="text-sm text-peach-800/60">Run a request to see live output.</p>
    );
  }
  return (
    <pre className="overflow-auto rounded-xl border border-peach-200 bg-white p-4 font-mono text-[13px] leading-relaxed text-peach-900">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Spinner() {
  return (
    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-peach-300 border-t-peach-500" />
  );
}

export function Button({
  children,
  loading,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }) {
  return (
    <button
      {...props}
      disabled={loading || props.disabled}
      className={`inline-flex items-center gap-2 rounded-lg bg-peach-400 px-4 py-2 text-sm font-medium text-peach-900 transition hover:bg-peach-300 disabled:cursor-not-allowed disabled:opacity-50 ${props.className || ""}`}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-xs uppercase tracking-[0.14em] text-peach-800/70">
        {label}
      </span>
      {children}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-peach-300 bg-white px-3 py-2 text-sm text-peach-900 outline-none ring-peach-400/40 placeholder:text-peach-300 focus:ring-2";
