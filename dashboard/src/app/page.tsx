import { Show, SignInButton, SignUpButton } from "@clerk/nextjs";
import Link from "next/link";

/**
 * Public landing page — deliberately reachable signed-out. The dashboard lives
 * behind auth at /dashboard; this page has to earn the click first.
 */

const METRICS = [
  {
    label: "Time to first audio",
    detail: "p50 / p95, measured from the first real audio frame — not the first text token.",
  },
  {
    label: "Barge-in talk-over",
    detail: "How much audio the agent pushed over the caller after being interrupted.",
  },
  {
    label: "Goal completion",
    detail: "Whether the caller's actual task got done, judged on the transcript.",
  },
];

export default function Landing() {
  return (
    <div className="space-y-16">
      <section className="pt-4">
        <p className="mb-3 inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950/50 dark:text-indigo-300">
          Open-source · runs in your CI
        </p>
        <h1 className="max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
          Catch the regression before your customers hear it.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-600 dark:text-slate-400">
          SoundCheck phones your voice agent with a simulated caller, interrupts it
          mid-sentence, and measures what a real customer feels. Then it fails your
          build when a change makes any of it worse.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Show when="signed-out">
            <SignUpButton mode="modal">
              <button className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500">
                Get started — it&apos;s free
              </button>
            </SignUpButton>
            <SignInButton mode="modal">
              <button className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-semibold transition hover:border-indigo-400 hover:text-indigo-600 dark:border-slate-700">
                Sign in
              </button>
            </SignInButton>
          </Show>
          <Show when="signed-in">
            <Link
              href="/dashboard"
              className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
            >
              Open dashboard →
            </Link>
          </Show>
          <a
            href="https://github.com/RickyVishwakarma/soundcheck"
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-semibold transition hover:border-indigo-400 hover:text-indigo-600 dark:border-slate-700"
          >
            View source
          </a>
        </div>
      </section>

      {/* The strongest thing this project has: a real finding from a real agent. */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="text-lg font-semibold">Found on a real ElevenLabs agent</h2>
        <p className="mt-1 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
          Timing an agent by when its events arrive is not the same as measuring what the
          caller hears. Audio streams faster than real time, so the caller is still being
          talked over long after the events say the agent stopped.
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-950/60">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Talk-over, by event timing
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">406 ms</p>
            <p className="mt-1 text-xs text-slate-500">looks fine</p>
          </div>
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-900 dark:bg-rose-950/40">
            <p className="text-xs uppercase tracking-wide text-rose-600 dark:text-rose-400">
              Talk-over, by decoded audio
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-rose-700 dark:text-rose-300">
              1,753 ms
            </p>
            <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">4× worse</p>
          </div>
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-950/60">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              First-audio p95
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">5,469 ms</p>
            <p className="mt-1 text-xs text-slate-500">
              reproducible; a manual test hits the fast path
            </p>
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">What it measures</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          {METRICS.map((m) => (
            <div
              key={m.label}
              className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
            >
              <p className="font-medium">{m.label}</p>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{m.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">How it works</h2>
        <ol className="mt-4 space-y-3 text-sm text-slate-600 dark:text-slate-400">
          {[
            "Write a caller as a short YAML script — including adversarial behaviour like interrupting, going silent, or switching language mid-call.",
            "SoundCheck runs it against your agent (or a deterministic mock that needs no API key) and times every turn from the real audio stream.",
            "Each run is compared to the previous one. Latency may drift within a tolerance; goal completion may never regress.",
            "In CI it fails the build and comments the delta on the pull request, so a bad prompt change never reaches a customer.",
          ].map((step, i) => (
            <li key={i} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white">
                {i + 1}
              </span>
              <span className="pt-0.5">{step}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-center sm:p-8 dark:border-slate-800 dark:bg-slate-900/60">
        <h2 className="text-xl font-semibold">Run your first test in about a minute</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-slate-600 dark:text-slate-400">
          Start with the built-in mock agent — no API key needed. Point it at your own
          ElevenLabs agent when you&apos;re ready; credentials are used for that run only
          and never stored.
        </p>
        <div className="mt-5 flex justify-center">
          <Show when="signed-out">
            <SignUpButton mode="modal">
              <button className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500">
                Create a free account
              </button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <Link
              href="/dashboard"
              className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
            >
              Open dashboard →
            </Link>
          </Show>
        </div>
      </section>
    </div>
  );
}
