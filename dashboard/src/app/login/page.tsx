"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") await signup(email.trim(), password);
      else await login(email.trim(), password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-bold tracking-tight">
        {mode === "signup" ? "Create your account" : "Sign in"}
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        Your runs, scenarios and agents, kept to your account. The public demo needs no
        sign-in.
      </p>

      <form onSubmit={submit} className="mt-6 space-y-4">
        <label className="block">
          <span className="text-sm font-medium">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Password</span>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          {mode === "signup" ? (
            <span className="mt-1 block text-xs text-slate-400">At least 8 characters.</span>
          ) : null}
        </label>

        {error ? <p className="text-sm text-rose-600">{error}</p> : null}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {busy ? "…" : mode === "signup" ? "Create account" : "Sign in"}
        </button>
      </form>

      <p className="mt-4 text-center text-sm text-slate-500">
        {mode === "signup" ? "Already have an account?" : "New here?"}{" "}
        <button
          onClick={() => {
            setMode(mode === "signup" ? "login" : "signup");
            setError(null);
          }}
          className="font-medium text-indigo-600 hover:underline"
        >
          {mode === "signup" ? "Sign in" : "Create one"}
        </button>
      </p>
    </div>
  );
}
