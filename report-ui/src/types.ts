/** Shapes mirror the JSON written by `soundcheck run` / committed baselines. */

export interface Turn {
  user: string;
  behavior: string | null;
  agent: string;
  ttfa_ms: number;
  total_ms: number;
  recovery_ms: number | null;
}

export interface Metrics {
  turn_count: number;
  ttfa_ms_p50: number;
  ttfa_ms_p95: number;
  turn_ms_p50: number;
  turn_ms_p95: number;
  recovery_ms_p95: number | null;
  goal_completed: boolean | null;
}

export interface RunReport {
  soundcheck_version: string;
  persona: string;
  goal: string;
  generated_at: string;
  turns: Turn[];
  metrics: Metrics;
}

/** Injected by `soundcheck html` in place of the placeholder. */
export interface Payload {
  baseline: RunReport;
  report: RunReport;
  failures: string[];
  tolerance: number;
}

declare global {
  interface Window {
    __SOUNDCHECK_DATA__: Payload | null;
  }
}
