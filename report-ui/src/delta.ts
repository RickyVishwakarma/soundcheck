import type { Metrics } from "./types";

/** Latency keys the gate enforces — keep in lockstep with soundcheck/gate.py. */
export const LATENCY_KEYS = [
  "ttfa_ms_p50",
  "ttfa_ms_p95",
  "turn_ms_p50",
  "turn_ms_p95",
  "recovery_ms_p95",
] as const;

export type LatencyKey = (typeof LATENCY_KEYS)[number];

export interface Row {
  key: string;
  baseline: string;
  current: string;
  delta: string;
  failed: boolean;
}

/** The verdict itself comes from the injected `failures` (the Python gate is
 *  the source of truth); this only derives per-row presentation. */
export function buildRows(base: Metrics, cur: Metrics, failures: string[]): Row[] {
  const failedKeys = new Set(failures.map((f) => f.split(" ")[0]));
  const rows: Row[] = [];

  for (const key of LATENCY_KEYS) {
    const b = base[key];
    const c = cur[key];
    if (b == null && c == null) continue;
    const delta =
      b != null && b !== 0 && c != null
        ? `${c / b - 1 >= 0 ? "+" : ""}${((c / b - 1) * 100).toFixed(0)}%`
        : "—";
    rows.push({
      key,
      baseline: b != null ? `${b} ms` : "—",
      current: c != null ? `${c} ms` : "—",
      delta,
      failed: failedKeys.has(key),
    });
  }

  if (base.goal_completed != null || cur.goal_completed != null) {
    rows.push({
      key: "goal_completed",
      baseline: String(base.goal_completed),
      current: String(cur.goal_completed),
      delta: "—",
      failed: failedKeys.has("goal_completed"),
    });
  }
  return rows;
}
