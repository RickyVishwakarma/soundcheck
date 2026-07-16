# SoundCheck — a reliability harness for voice agents

**Stress-test conversational voice agents before they talk to a real customer.**
Simulated callers hammer an agent with interruptions, topic changes, and bad audio
manners; SoundCheck measures what actually matters — time-to-first-audio, turn
latency, interruption recovery, goal completion — scores every transcript with an
LLM judge, and **fails your CI build when an agent config change regresses**.

> Voice-agent platforms make it easy to *build* an agent. Almost nothing exists to
> prove an agent is *ready*. SoundCheck is the missing pre-production gate: the
> soundcheck before the show.

## Status

The offline pipeline (mock agent → scripted personas → metrics → regression gate)
runs end-to-end with **zero API keys**, and the live ElevenLabs Agents transport
is implemented — same personas, same metrics, real WebSocket.

- [x] Scripted caller personas (YAML)
- [x] Metrics: TTFA, turn latency percentiles, goal completion
- [x] Regression gate with committed baselines (CI-ready, exit codes)
- [x] Deterministic offline mode — full pipeline with no external services
- [x] Live transport: ElevenLabs Agents (WebSocket, TTFA from first audio event)
- [x] Interruption injection: barge-in mid-reply + `recovery_ms` (how long the
      agent keeps talking over you) — measured, baselined, and gated
- [ ] GitHub Action that comments the reliability delta on your PR
- [ ] Static HTML regression report (shareable, CI-artifact friendly)
- [ ] LLM-driven personas and LLM-judge evals (roadmap; the gate stays deterministic)

## Quickstart (no API keys)

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt

# Run a simulated caller against the built-in mock agent
python -m soundcheck.cli run --persona personas/appointment_booking.yaml --offline --out report.json

# Gate: compare against the committed baseline; non-zero exit on regression
python -m soundcheck.cli gate --baseline baselines/appointment_booking.json --report report.json
```

With `ELEVENLABS_API_KEY` and an agent id set, the same personas run against a real
ElevenLabs agent over WebSocket — one pipeline, two transports, so results are
comparable across mock and live (the same research-to-production discipline as my
trading platform [Quantis](https://github.com/RickyVishwakarma/quantis)).

## Architecture

```
persona (YAML / LLM)          transport                     analysis
┌────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ scripted turns      │   │ MockAgent (offline)  │   │ metrics: TTFA, turn  │
│ behaviors:          ├──▶│ ElevenLabs Agents WS ├──▶│ latency p50/p95,     │
│  interrupt/offtopic │   │ (same interface)     │   │ goal completion      │
│ success criteria    │   └──────────────────────┘   │ LLM-judge evals      │
└────────────────────┘                               └──────────┬───────────┘
                                                                ▼
                                            regression gate ── CI (exit 1 on drift)
```

Design rules carried over from my previous systems:

- **One code path** — mock and live differ only in which `AgentTransport` is constructed.
- **Deterministic by default** — seeded latencies and scripted replies offline, so CI is free and flake-less.
- **The gate is the product** — every metric exists to answer one question: *did this change make the agent worse?*

## Repo layout

| Path | What |
|---|---|
| `soundcheck/session.py` | `AgentTransport` protocol; mock + ElevenLabs implementations |
| `soundcheck/personas/` | Persona schema, scripted runner, (planned) LLM personas |
| `soundcheck/runner.py` | Drives persona × transport → timed transcript |
| `soundcheck/metrics.py` | TTFA, latency percentiles, goal completion |
| `soundcheck/evals/` | LLM-judge transcript scoring, heuristic local fallback |
| `soundcheck/gate.py` | Baseline comparison, thresholds, exit codes |
| `personas/` | Example caller personas (YAML) |
| `baselines/` | Committed metric baselines the gate compares against |
| `dashboard/` | (planned) Next.js trace viewer |

## Why I'm building this

I build systems that refuse to let bad things ship quietly — a trading platform
whose model registry refused my own model production access
([Quantis](https://github.com/RickyVishwakarma/quantis)), and an LLM gateway with
an eval gate in CI (Sentinel). Voice agents are the next place where "it demoed
fine" meets production reality, and the tooling gap is obvious. SoundCheck is my
attempt to close it.

MIT licensed.
