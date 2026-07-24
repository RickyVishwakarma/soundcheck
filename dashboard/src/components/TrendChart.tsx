"use client";

import { useEffect, useState } from "react";
import { api, ms, type TrendPoint } from "@/lib/api";

/**
 * A dependency-free SVG line of TTFA p95 over a scenario's run history —
 * enough to show drift without pulling in a charting library. Points are
 * colored by gate status so a red dot marks the run that regressed.
 */
export function TrendChart({ persona }: { persona: string }) {
  const [points, setPoints] = useState<TrendPoint[] | null>(null);

  useEffect(() => {
    api.trend(persona).then(setPoints).catch(() => setPoints([]));
  }, [persona]);

  if (!points || points.length < 2) return null;

  const values = points.map((p) => p.ttfa_ms_p95 ?? 0);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const W = 600;
  const H = 120;
  const pad = 12;

  const x = (i: number) => pad + (i / (points.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - min) / range) * (H - 2 * pad);

  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p.ttfa_ms_p95 ?? 0).toFixed(1)}`)
    .join(" ");

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">
          Time-to-first-audio p95 over time — <code className="text-indigo-600">{persona}</code>
        </h2>
        <span className="text-sm text-slate-500">{points.length} runs</span>
      </div>
      <p className="mb-3 text-sm text-slate-500">
        Drift you would never see from a single run. Red points failed the gate.
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="TTFA trend">
        <path d={path} fill="none" stroke="#a5b4fc" strokeWidth="2" />
        {points.map((p, i) => (
          <circle
            key={p.id}
            cx={x(i)}
            cy={y(p.ttfa_ms_p95 ?? 0)}
            r={3.5}
            fill={p.status === "failed" ? "#e11d48" : "#4f46e5"}
          >
            <title>
              {p.created_at.replace("T", " ").replace("+00:00", "")} — {ms(p.ttfa_ms_p95)} (
              {p.status})
            </title>
          </circle>
        ))}
      </svg>
      <div className="mt-2 flex justify-between text-xs text-slate-400">
        <span>{ms(min)}</span>
        <span>{ms(max)}</span>
      </div>
    </section>
  );
}
