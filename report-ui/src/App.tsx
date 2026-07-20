import type { Payload, Turn } from "./types";
import { buildRows } from "./delta";
import { DEMO } from "./demo";

const LABELS: Record<string, string> = {
  ttfa_ms_p50: "Time to first audio · p50",
  ttfa_ms_p95: "Time to first audio · p95",
  turn_ms_p50: "Turn latency · p50",
  turn_ms_p95: "Turn latency · p95",
  recovery_ms_p95: "Barge-in recovery · p95",
  goal_completed: "Goal completed",
};

function Verdict({ failures }: { failures: string[] }) {
  const passed = failures.length === 0;
  return (
    <div className={`verdict ${passed ? "pass" : "fail"}`}>
      <span className="verdict-word">{passed ? "GATE PASSED" : "GATE FAILED"}</span>
      {passed ? (
        <span>no regressions against the baseline</span>
      ) : (
        <ul>
          {failures.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DeltaTable({ data }: { data: Payload }) {
  const built = buildRows(data.baseline.metrics, data.report.metrics, data.failures);
  return (
    <table className="delta">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Baseline</th>
          <th>This run</th>
          <th>Δ</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {built.map((r) => (
          <tr key={r.key} className={r.failed ? "row-fail" : ""}>
            <td>
              {LABELS[r.key] ?? r.key}
              <span className="key">{r.key}</span>
            </td>
            <td className="num">{r.baseline}</td>
            <td className="num">{r.current}</td>
            <td className="num">{r.delta}</td>
            <td className="mark">{r.failed ? "✗" : "✓"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function LatencyBar({ turn, maxMs }: { turn: Turn; maxMs: number }) {
  const ttfaPct = (turn.ttfa_ms / maxMs) * 100;
  const restPct = ((turn.total_ms - turn.ttfa_ms) / maxMs) * 100;
  return (
    <div className="bar" title={`TTFA ${turn.ttfa_ms} ms · total ${turn.total_ms} ms`}>
      <div className="bar-ttfa" style={{ width: `${ttfaPct}%` }} />
      <div className="bar-rest" style={{ width: `${restPct}%` }} />
      <span className="bar-label">{Math.round(turn.total_ms)} ms</span>
    </div>
  );
}

function Turns({ turns }: { turns: Turn[] }) {
  if (turns.length === 0) return null;
  const maxMs = Math.max(...turns.map((t) => t.total_ms));
  return (
    <ol className="turns">
      {turns.map((t, i) => (
        <li key={i} className="turn">
          <div className="line user-line">
            <span className="speaker">caller</span>
            <span className="utterance">
              {t.user}
              {t.behavior && <span className={`badge badge-${t.behavior}`}>{t.behavior}</span>}
            </span>
          </div>
          <div className="line agent-line">
            <span className="speaker">agent</span>
            <span className="utterance">{t.agent}</span>
          </div>
          <LatencyBar turn={t} maxMs={maxMs} />
          {t.recovery_ms != null && (
            <div className="recovery">
              kept talking <strong>{t.recovery_ms} ms</strong> after the barge-in
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

export default function App() {
  const data = window.__SOUNDCHECK_DATA__ ?? DEMO;
  const isDemo = window.__SOUNDCHECK_DATA__ == null;
  const r = data.report;
  return (
    <main>
      <header>
        <h1>
          <span className="logo">🔊</span> SoundCheck
          {isDemo && <span className="demo-chip">demo data</span>}
        </h1>
        <p className="sub">
          <code>{r.persona}</code> — {r.goal}
        </p>
        <p className="meta">
          {r.turns.length || r.metrics.turn_count} turns · generated {r.generated_at} · v
          {r.soundcheck_version} · tolerance +{Math.round(data.tolerance * 100)}%
        </p>
      </header>
      <Verdict failures={data.failures} />
      <section>
        <h2>Metrics vs baseline</h2>
        <DeltaTable data={data} />
      </section>
      <section>
        <h2>Conversation</h2>
        <p className="hint">
          Bars show time-to-first-audio (dark) then the rest of the reply. Interrupted turns
          report how long the agent kept talking over the caller.
        </p>
        <Turns turns={r.turns} />
      </section>
      <footer>
        SoundCheck — the CI-native reliability gate for voice agents ·{" "}
        <a href="https://github.com/RickyVishwakarma/soundcheck">github.com/RickyVishwakarma/soundcheck</a>
      </footer>
    </main>
  );
}
