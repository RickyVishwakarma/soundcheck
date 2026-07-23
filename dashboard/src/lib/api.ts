/** Types mirror the FastAPI responses in server/app.py. */

export const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8077";

export interface Metrics {
  turn_count: number;
  ttfa_ms_p50: number;
  ttfa_ms_p95: number;
  turn_ms_p50: number;
  turn_ms_p95: number;
  recovery_ms_p95: number | null;
  talkover_ms_p95: number | null;
  speech_ms_total: number | null;
  goal_completed: boolean | null;
}

export interface Turn {
  user: string;
  behavior: string | null;
  agent: string;
  ttfa_ms: number;
  total_ms: number;
  recovery_ms: number | null;
  speech_ms: number | null;
  talkover_ms: number | null;
}

export interface Report {
  soundcheck_version: string;
  persona: string;
  goal: string;
  generated_at: string;
  turns: Turn[];
  metrics: Metrics;
}

export type RunStatus = "queued" | "running" | "passed" | "failed" | "error";

export interface Run {
  id: string;
  persona: string;
  mode: "demo" | "live";
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  failures: string[];
  metrics: Metrics | null;
  report?: Report | null;
}

export interface PersonaSummary {
  name: string;
  goal: string;
  turns: number;
  behaviors: string[];
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  personas: () => fetch(`${API}/api/personas`, { cache: "no-store" }).then(json<PersonaSummary[]>),

  runs: () => fetch(`${API}/api/runs`, { cache: "no-store" }).then(json<Run[]>),

  run: (id: string) => fetch(`${API}/api/runs/${id}`, { cache: "no-store" }).then(json<Run>),

  start: (body: {
    mode: "demo" | "live";
    persona_name?: string;
    agent_id?: string;
    api_key?: string;
    latency_bias_ms?: number;
  }) =>
    fetch(`${API}/api/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<{ id: string; status: string }>),
};

export const ms = (v: number | null | undefined) =>
  v == null ? "—" : `${Math.round(v).toLocaleString()} ms`;
