"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ms, type Run } from "@/lib/api";
import { StatusPill } from "./StatusPill";

const METRIC_LABELS: Record<string, string> = {
  ttfa_ms_p50: "Time to first audio · p50",
  ttfa_ms_p95: "Time to first audio · p95",
  turn_ms_p50: "Turn latency · p50",
  turn_ms_p95: "Turn latency · p95",
  recovery_ms_p95: "Barge-in recovery · p95",
  talkover_ms_p95: "Talk-over (real audio) · p95",
  speech_ms_total: "Agent speech · total",
};

export function RunDetail({ id }: { id: string }) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const r = await api.run(id);
        if (!alive) return;
        setRun(r);
        // Keep polling only while the run is still executing.
        if (r.status === "queued" || r.status === "running") {
          timer = setTimeout(poll, 1000);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Could not load run");
      }
    }
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!run) return <p className="text-sm text-slate-500">Loading run…</p>;

  const inFlight = run.status === "queued" || run.status === "running";
  const report = run.report;

  return (
    <div className="space-y-8">
      <div>
        <Link href="/" className="text-sm text-indigo-600 hover:underline">
          ← All runs
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{run.persona}</h1>
          <StatusPill status={run.status} />
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-800">
            {run.mode}
          </span>
        </div>
        {report?.goal ? (
          <p className="mt-1 text-sm text-slate-500">{report.goal}</p>
        ) : null}
      </div>

      {inFlight ? (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-6 dark:border-amber-800 dark:bg-amber-950/30">
          <p className="font-medium">The simulated caller is on the phone…</p>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            A live agent takes ~30 seconds for a four-turn call. Results appear here
            automatically.
          </p>
        </div>
      ) : null}

      {run.status === "error" ? (
        <pre className="overflow-x-auto rounded-xl border border-rose-300 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200">
          {run.error}
        </pre>
      ) : null}

      {run.failures.length > 0 ? (
        <div className="rounded-xl border border-rose-300 bg-rose-50 p-5 dark:border-rose-900 dark:bg-rose-950/30">
          <p className="font-semibold text-rose-700 dark:text-rose-300">
            This change makes the agent worse
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-rose-700 dark:text-rose-300">
            {run.failures.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {run.metrics ? (
        <section>
          <h2 className="mb-3 text-lg font-semibold">Metrics</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(METRIC_LABELS).map(([key, label]) => {
              const value = run.metrics![key as keyof typeof run.metrics] as number | null;
              const bad = run.failures.some((f) => f.startsWith(key));
              return (
                <div
                  key={key}
                  className={`rounded-xl border p-4 ${
                    bad
                      ? "border-rose-300 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/30"
                      : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
                  }`}
                >
                  <p className="text-xs text-slate-500">{label}</p>
                  <p className="mt-1 text-xl font-semibold tabular-nums">{ms(value)}</p>
                </div>
              );
            })}
            <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
              <p className="text-xs text-slate-500">Goal completed</p>
              <p className="mt-1 text-xl font-semibold">
                {run.metrics.goal_completed == null
                  ? "—"
                  : run.metrics.goal_completed
                    ? "Yes"
                    : "No"}
              </p>
            </div>
          </div>
        </section>
      ) : null}

      {report?.turns?.length ? (
        <section>
          <h2 className="mb-1 text-lg font-semibold">Conversation</h2>
          <p className="mb-3 text-sm text-slate-500">
            Bars show time to first audio (dark) then the rest of the reply.
          </p>
          <ol className="space-y-3">
            {report.turns.map((t, i) => {
              const max = Math.max(...report.turns.map((x) => x.total_ms));
              return (
                <li
                  key={i}
                  className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
                >
                  <p className="text-sm">
                    <span className="mr-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      caller
                    </span>
                    {t.user}
                    {t.behavior ? (
                      <span className="ml-2 rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700 dark:bg-orange-900/40 dark:text-orange-300">
                        {t.behavior}
                      </span>
                    ) : null}
                  </p>
                  <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                    <span className="mr-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      agent
                    </span>
                    {t.agent}
                  </p>
                  <div className="mt-3 flex h-4 overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
                    <div
                      className="bg-indigo-900"
                      style={{ width: `${(t.ttfa_ms / max) * 100}%` }}
                      title={`TTFA ${Math.round(t.ttfa_ms)} ms`}
                    />
                    <div
                      className="bg-indigo-300"
                      style={{ width: `${((t.total_ms - t.ttfa_ms) / max) * 100}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-slate-500">
                    first audio {ms(t.ttfa_ms)} · turn {ms(t.total_ms)}
                    {t.speech_ms ? ` · speech ${ms(t.speech_ms)}` : ""}
                  </p>
                  {t.talkover_ms != null ? (
                    <p className="mt-1 text-xs font-medium text-orange-600 dark:text-orange-400">
                      kept talking over the caller for {ms(t.talkover_ms)} of real audio
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
