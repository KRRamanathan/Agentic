import type { ReactNode } from "react";
import Link from "next/link";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/observability", label: "Observability" },
  { href: "/insights", label: "Cost & Memory" },
];

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-peach-50 text-peach-900">
      <header className="border-b border-peach-200 bg-peach-100/70">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <Link href="/" className="text-sm tracking-[0.2em] uppercase text-peach-800">
            Agentic
          </Link>
          <nav className="flex gap-6 text-sm text-peach-800/80">
            {LINKS.map((link) => (
              <Link key={link.href} href={link.href} className="hover:text-peach-900">
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-12">{children}</main>
    </div>
  );
}
