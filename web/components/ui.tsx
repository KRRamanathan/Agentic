"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

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
