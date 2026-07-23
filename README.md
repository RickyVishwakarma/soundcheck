# SoundCheck — a reliability harness for voice agents

**Stress-test conversational voice agents before they talk to a real customer.**
Simulated callers hammer an agent with interruptions and topic changes; SoundCheck
measures what actually matters — time-to-first-audio, turn latency, interruption
recovery, goal completion — and **fails your CI build when an agent config change
regresses**, commenting the delta on the pull request.

> Voice-agent platforms make it easy to *build* an agent. Almost nothing exists to
> prove an agent is *ready*. SoundCheck is the missing pre-production gate: the
> soundcheck before the show.

📉 **See it catch a real regression:** [CASE_STUDY.md](CASE_STUDY.md) — a bloated
prompt that still books the appointment but adds 62% latency, blocked by the gate.

## Status

The offline pipeline (mock agent → scripted personas → metrics → regression gate)
runs end-to-end with **zero API keys**, and the live ElevenLabs Agents transport
is **verified against a real agent** — same personas, same metrics, real WebSocket.

### Verified live run

Against a real ElevenLabs agent (a dental-clinic receptionist), the
`appointment_booking` persona completed its goal — the agent replied
*"Alright, Ricky. You're booked for Tuesday at ten AM, confirmed."*

| Metric | Live agent | Note |
|---|---:|---|
| ttfa_ms_p50 | 1383 ms | |
| ttfa_ms_p95 | **5469 ms** | one turn stalled 5.5s before speaking |
| turn_ms_p95 | 6453 ms | |
| goal_completed | ✅ true | |

That p95 is the whole argument for this tool: the agent felt fine on three
turns and hung for **five and a half seconds** on the fourth. A manual test
would have hit the fast path and shipped it. Barge-in was verified live too —
the agent kept talking **140 ms** and **328 ms** past the caller's interruption
on the two `interrupt` turns.

Raw reports: [`examples/`](examples/).

### Why it decodes the audio (and what that changed)

SoundCheck decodes the PCM stream the agent sends rather than inferring
everything from event arrival times. Running the `impatient_refund` persona
live surfaced why that matters:

| Turn 4 (caller barges in) | Value |
|---|---:|
| `recovery_ms` — wall-clock until audio stopped | 406 ms |
| `talkover_ms` — **real audio delivered after the barge-in** | **1752.9 ms** |

The event-timing metric understated the problem **by more than 4×**. The agent
streams audio faster than real time, so nearly two seconds of speech had
already been delivered — and that is what the caller actually hears on top of
their own voice. A harness that only times events reports 406 ms and calls it
fine.

`--save-audio DIR` writes each agent turn as a playable 16 kHz WAV
([`examples/audio/`](examples/audio/)), so a reviewer can listen to exactly
what the metric describes.

- [x] Scripted caller personas (YAML)
- [x] Metrics: TTFA, turn latency percentiles, goal completion
- [x] Regression gate with committed baselines (CI-ready, exit codes)
- [x] Deterministic offline mode — full pipeline with no external services
- [x] Live transport: ElevenLabs Agents (WebSocket, TTFA from first audio event)
- [x] Interruption injection: barge-in mid-reply + `recovery_ms` (how long the
      agent keeps talking over you) — measured, baselined, and gated
- [x] **Real audio analysis** — decodes the PCM stream for `speech_ms` and
      `talkover_ms` (actual audio delivered after a barge-in), plus WAV
      recordings via `--save-audio`
- [x] `pip install`-able package with a `soundcheck` console command
- [x] GitHub Action that gates the build and comments the reliability delta on your PR
- [x] Static HTML regression report (`soundcheck html`) — React/TypeScript UI
      compiled to one self-contained file; verdict, delta table, per-turn latency
      bars, and barge-in recovery callouts. CI-artifact friendly, opens anywhere.
- [ ] LLM-driven personas and LLM-judge evals (roadmap; the gate stays deterministic)

## Quickstart (no API keys)

```bash
pip install "soundcheck[live] @ git+https://github.com/RickyVishwakarma/soundcheck.git"

# Run a simulated caller against the built-in mock agent
soundcheck run --persona personas/appointment_booking.yaml --offline --out report.json

# Gate: compare against the committed baseline; non-zero exit on regression
soundcheck gate --baseline baselines/appointment_booking.json --report report.json

# Render the delta as markdown (what the GitHub Action posts on your PR)
soundcheck diff --baseline baselines/appointment_booking.json --report report.json

# Or a self-contained HTML report: verdict, delta table, per-turn latency bars
soundcheck html --baseline baselines/appointment_booking.json --report report.json
```

The HTML report is a React/TypeScript app (source in `report-ui/`) compiled to a
single file and committed as the package template — pip users never need Node.

## Use it as a GitHub Action

One step in your workflow: run a persona, gate the build, and — on pull
requests — comment the reliability delta:

```yaml
- uses: RickyVishwakarma/soundcheck@master
  with:
    persona: personas/impatient_refund.yaml
    baseline: baselines/impatient_refund.json
```

What the PR comment looks like when a change makes the agent slower to shut
up after a barge-in:

| Metric | Baseline | This run | Δ | |
|---|---:|---:|---:|:--:|
| ttfa_ms_p95 | 401.8 | 309.3 | -23% | ✅ |
| turn_ms_p95 | 1560.3 | 1693.1 | +9% | ✅ |
| recovery_ms_p95 | 327.7 | 416.0 | +27% | ❌ |
| goal_completed | True | True | — | ✅ |

**GATE FAILED** — `recovery_ms_p95` regressed: 327.7 → 416.0 ms (+27%, tolerance +20%)

This repo's own CI runs the Action on itself — the harness gates the harness.

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
