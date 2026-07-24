"use client";

import { SignInButton, useUser } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";
import { api, type SavedAgent } from "@/lib/api";

export default function SettingsPage() {
  const { user, isSignedIn, isLoaded } = useUser();
  const ready = isLoaded;
  const email = user?.primaryEmailAddress?.emailAddress ?? null;
  const [agents, setAgents] = useState<SavedAgent[]>([]);
  const [label, setLabel] = useState("");
  const [agentId, setAgentId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadAgents = useCallback(() => {
    api.agents().then(setAgents).catch(() => setAgents([]));
  }, []);

  useEffect(() => {
    if (ready && isSignedIn) loadAgents();
  }, [ready, isSignedIn, loadAgents]);

  if (ready && !isSignedIn) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm dark:border-slate-800 dark:bg-slate-900">
        <p className="font-medium">Settings need an account.</p>
        <SignInButton mode="modal">
          <button className="mt-2 inline-block text-indigo-600 hover:underline">
            Sign in →
          </button>
        </SignInButton>
      </div>
    );
  }

  async function addAgent(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createAgent(label.trim(), agentId.trim());
      setLabel("");
      setAgentId("");
      loadAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">{email}</p>
      </div>

      <section>
        <h2 className="text-lg font-semibold">Saved agents</h2>
        <p className="mt-1 text-sm text-slate-500">
          Store an ElevenLabs agent id so you don&apos;t paste it every run. The API key is
          never saved — you provide it at run time and it&apos;s used for that request only.
        </p>

        <form onSubmit={addAgent} className="mt-4 flex flex-wrap gap-2">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (e.g. Production)"
            required
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <input
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            placeholder="agent_xxxxxxxx"
            required
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <button className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500">
            Save
          </button>
        </form>
        {error ? <p className="mt-2 text-sm text-rose-600">{error}</p> : null}

        <ul className="mt-4 space-y-2">
          {agents.length === 0 ? (
            <li className="rounded-lg border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500 dark:border-slate-700">
              No saved agents yet.
            </li>
          ) : (
            agents.map((a) => (
              <li
                key={a.id}
                className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-900"
              >
                <div>
                  <span className="font-medium">{a.label}</span>
                  <code className="ml-3 text-xs text-slate-500">{a.agent_id}</code>
                </div>
                <button
                  onClick={() => api.deleteAgent(a.id).then(loadAgents)}
                  className="text-xs text-rose-600 hover:underline"
                >
                  Remove
                </button>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}
