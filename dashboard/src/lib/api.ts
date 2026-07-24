/** Types mirror the FastAPI responses in server/app.py. */

export const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8077";

// Clerk hands out session tokens through an async hook, but this module is
// framework-agnostic. A top-level component registers Clerk's getToken here,
// so api calls can attach the current token without importing React.
let tokenGetter: (() => Promise<string | null>) | null = null;

export function setTokenGetter(fn: (() => Promise<string | null>) | null): void {
  tokenGetter = fn;
}

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
  hallucinated: boolean | null;
  instruction_following: number | null;
  tone: number | null;
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
  source: "bundled" | "saved";
  id?: string;
}

export interface SavedAgent {
  id: string;
  label: string;
  agent_id: string;
  created_at: string;
}

export interface TrendPoint {
  id: string;
  created_at: string;
  status: RunStatus;
  ttfa_ms_p95: number | null;
  turn_ms_p95: number | null;
  talkover_ms_p95: number | null;
  goal_completed: boolean | null;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenGetter ? await tokenGetter() : null;
  const res = await fetch(`${API}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  // Auth is handled by Clerk on the frontend; the backend verifies Clerk's
  // session token, so there are no signup/login endpoints here anymore.

  // scenarios & agents
  personas: () => req<PersonaSummary[]>("/api/personas"),
  createScenario: (spec: object) =>
    req<{ id: string; name: string }>("/api/scenarios", {
      method: "POST",
      body: JSON.stringify(spec),
    }),
  deleteScenario: (id: string) =>
    req<void>(`/api/scenarios/${id}`, { method: "DELETE" }),
  agents: () => req<SavedAgent[]>("/api/agents"),
  createAgent: (label: string, agent_id: string) =>
    req<SavedAgent>("/api/agents", {
      method: "POST",
      body: JSON.stringify({ label, agent_id }),
    }),
  deleteAgent: (id: string) => req<void>(`/api/agents/${id}`, { method: "DELETE" }),

  // runs & trends
  runs: () => req<Run[]>("/api/runs"),
  run: (id: string) => req<Run>(`/api/runs/${id}`),
  trend: (persona: string) => req<TrendPoint[]>(`/api/trends/${persona}`),
  start: (body: {
    mode: "demo" | "live";
    persona_name?: string;
    agent_id?: string;
    api_key?: string;
    latency_bias_ms?: number;
  }) =>
    req<{ id: string; status: string }>("/api/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const ms = (v: number | null | undefined) =>
  v == null ? "—" : `${Math.round(v).toLocaleString()} ms`;
