"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ms, type PersonaSummary, type Run } from "@/lib/api";
import { RunLauncher } from "./RunLauncher";
import { StatusPill } from "./StatusPill";

type Phase = "loading" | "waking" | "ready" | "down";

/**
 * Fetched client-side rather than in a server component: the API runs on a
 * free tier that sleeps after inactivity, and a cold start takes longer than
 * a serverless render is allowed to wait. Fetching here lets the page paint
 * immediately and honestly say "waking up" instead of "down".
 */
export function Dashboard() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [personas, setPersonas] = useState<PersonaSummary[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);

  const load = useCallback(async (attempt = 0) => {
    try {
      const [p, r] = await Promise.all([api.personas(), api.runs()]);
      setPersonas(p);
      setRuns(r);
      setPhase("ready");
    } catch {
      // A sleeping instance refuses connections until it boots; keep retrying
      // for ~90s before calling it genuinely down.
      if (attempt < 12) {
        setPhase("waking");
        setTimeout(() => load(attempt + 1), 8000);
      } else {
        setPhase("down");
      }
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const failing = runs.filter((r) => r.status === "failed").length;

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-3xl font-bold tracking-tight">
          Catch the regression before your customers hear it.
        </h1>
        <p className="mt-3 max-w-2xl text-slate-600 dark:text-slate-400">
          SoundCheck phones your voice agent with a simulated caller, interrupts it
          mid-sentence, and measures what a real customer feels — time to first audio,
          how long it talks over you, and whether the job actually got done. Then it
          fails your build when a change makes any of it worse.
        </p>
      </section>

      {phase === "loading" || phase === "waking" ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
          <p className="flex items-center gap-2 font-medium">
            <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
            {phase === "waking" ? "Waking the API…" : "Connecting…"}
          </p>
          {phase === "waking" ? (
            <p className="mt-1 text-sm text-slate-500">
              It sleeps when idle on the free tier, so the first request takes up to a
              minute. This page will fill in on its own.
            </p>
          ) : null}
        </div>
      ) : null}

      {phase === "down" ? (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-6 text-sm dark:border-amber-800 dark:bg-amber-950/40">
          <p className="font-semibold">Couldn&apos;t reach the SoundCheck API.</p>
          <p className="mt-1 text-slate-600 dark:text-slate-400">
            Running locally? Start it with{" "}
            <code className="rounded bg-white px-1.5 py-0.5 dark:bg-slate-900">
              uvicorn server.app:app --port 8077
            </code>{" "}
            from the repo root.
          </p>
          <button
            onClick={() => load()}
            className="mt-3 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500"
          >
            Retry
          </button>
        </div>
      ) : null}

      {phase === "ready" ? (
        <>
          <RunLauncher personas={personas} />

          <section>
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="text-lg font-semibold">Run history</h2>
              {runs.length > 0 ? (
                <p className="text-sm text-slate-500">
                  {runs.length} run{runs.length === 1 ? "" : "s"}
                  {failing > 0 ? ` · ${failing} failing` : ""}
                </p>
              ) : null}
            </div>

            {runs.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-slate-700">
                No runs yet. Start one above — the first run becomes the baseline, and
                every run after it is compared against the last.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950/60">
                    <tr>
                      <th className="px-4 py-3 font-semibold">Scenario</th>
                      <th className="px-4 py-3 font-semibold">Status</th>
                      <th className="px-4 py-3 text-right font-semibold">TTFA p95</th>
                      <th className="px-4 py-3 text-right font-semibold">Talk-over p95</th>
                      <th className="px-4 py-3 text-center font-semibold">Goal</th>
                      <th className="px-4 py-3 font-semibold">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr
                        key={r.id}
                        className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40"
                      >
                        <td className="px-4 py-3">
                          <Link
                            href={`/runs/${r.id}`}
                            className="font-medium text-indigo-600 hover:underline"
                          >
                            {r.persona}
                          </Link>
                          <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-800">
                            {r.mode}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <StatusPill status={r.status} />
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {ms(r.metrics?.ttfa_ms_p95)}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {ms(r.metrics?.talkover_ms_p95)}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {r.metrics?.goal_completed == null
                            ? "—"
                            : r.metrics.goal_completed
                              ? "✓"
                              : "✗"}
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          {r.created_at.replace("T", " ").replace("+00:00", "")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
