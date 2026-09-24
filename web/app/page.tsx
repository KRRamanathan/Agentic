import Link from "next/link";
import { MODULES } from "@/lib/api";

export default function HomePage() {
  return (
    <div className="space-y-10">
      <div className="max-w-2xl space-y-3">
        <p className="text-xs uppercase tracking-[0.18em] text-peach-500">Live playground</p>
        <h1 className="text-4xl font-medium tracking-tight text-peach-900">Ten agent modules</h1>
        <p className="text-peach-800/70">
          Each card talks to the FastAPI backend. Outputs are live responses, not samples.
        </p>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        {MODULES.map((mod) => (
          <article
            key={mod.slug}
            className="flex flex-col justify-between rounded-2xl border border-peach-200 bg-white p-6 shadow-sm"
          >
            <div className="space-y-3">
              <h2 className="text-lg font-medium text-peach-900">{mod.title}</h2>
              <p className="text-sm leading-relaxed text-peach-800/70">{mod.description}</p>
            </div>
            <Link
              href={mod.href}
              className="mt-8 inline-flex w-fit rounded-lg bg-peach-400 px-4 py-2 text-sm font-medium text-peach-900 hover:bg-peach-300"
            >
              Try it
            </Link>
          </article>
        ))}
      </div>
    </div>
  );
}
