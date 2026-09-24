"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useLlmConfig } from "@/components/ConfigProvider";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/observability", label: "Observability" },
  { href: "/insights", label: "Cost & Memory" },
];

export function Shell({ children }: { children: ReactNode }) {
  const { llm_mode } = useLlmConfig();
  const fake = llm_mode !== "real";
  const label = llm_mode === "real" ? "Live model" : "Demo mode";
  const tip =
    llm_mode === "real"
      ? "Connected to the live model."
      : "Scripted model. No API key required.";

  return (
    <div className="min-h-screen bg-peach-50 text-peach-900">
      <header className="border-b border-peach-200 bg-peach-100/70">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <Link href="/" className="text-sm tracking-[0.2em] uppercase text-peach-800">
            Agentic
          </Link>
          <div className="flex items-center gap-6">
            <nav className="flex gap-6 text-sm text-peach-800/80">
              {LINKS.map((link) => (
                <Link key={link.href} href={link.href} className="hover:text-peach-900">
                  {link.label}
                </Link>
              ))}
            </nav>
            <span
              title={tip}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                fake
                  ? "bg-stone-200 text-stone-600"
                  : "bg-emerald-100 text-emerald-800"
              }`}
            >
              {label}
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-12">{children}</main>
    </div>
  );
}
