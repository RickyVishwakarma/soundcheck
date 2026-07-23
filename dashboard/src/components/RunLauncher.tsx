"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type PersonaSummary } from "@/lib/api";

export function RunLauncher({ personas }: { personas: PersonaSummary[] }) {
  const router = useRouter();
  const [persona, setPersona] = useState(personas[0]?.name ?? "");
  const [live, setLive] = useState(false);
  const [agentId, setAgentId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [degrade, setDegrade] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = personas.find((p) => p.name === persona);

  async function launch() {
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.start({
        mode: live ? "live" : "demo",
        persona_name: persona,
        ...(live ? { agent_id: agentId.trim(), api_key: apiKey.trim() } : {}),
        ...(!live && degrade ? { latency_bias_ms: 250 } : {}),
      });
      router.push(`/runs/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run");
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="text-lg font-semibold">Run a test</h2>
      <p className="mt-1 text-sm text-slate-500">
        A simulated caller phones your agent, interrupts it, and times everything.
      </p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium">Scenario</span>
          <select
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            {personas.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <div className="text-sm">
          <span className="font-medium">Caller goal</span>
          <p className="mt-1 text-slate-500">{selected?.goal || "—"}</p>
          {selected?.behaviors.length ? (
            <p className="mt-2 flex flex-wrap gap-1">
              {selected.behaviors.map((b) => (
                <span
                  key={b}
                  className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700 dark:bg-orange-900/40 dark:text-orange-300"
                >
                  {b}
                </span>
              ))}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-5 space-y-3 rounded-lg bg-slate-50 p-4 dark:bg-slate-950/60">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
          <span>
            Test <strong>my real agent</strong> (ElevenLabs)
          </span>
        </label>

        {live ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              placeholder="agent_xxxxxxxx"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type="password"
              placeholder="ElevenLabs API key"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <p className="sm:col-span-2 text-xs text-slate-500">
              Used for this run only — never stored on the server or written to logs.
            </p>
          </div>
        ) : (
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <input
              type="checkbox"
              checked={degrade}
              onChange={(e) => setDegrade(e.target.checked)}
            />
            <span>
              Simulate a degraded config (+250 ms) — watch the gate catch it
            </span>
          </label>
        )}
      </div>

      {error ? <p className="mt-3 text-sm text-rose-600">{error}</p> : null}

      <button
        onClick={launch}
        disabled={busy || (live && (!agentId.trim() || !apiKey.trim()))}
        className="mt-5 w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
      >
        {busy ? "Starting…" : live ? "Run against my agent" : "Run test — no signup"}
      </button>
    </section>
  );
}
