# Case study: catching a regression a manual test would miss

A voice-agent team tweaks their agent's system prompt — adds a few paragraphs
of instructions to make it "more helpful." They try it once by hand, it books
the appointment, it *sounds* fine. They ship it.

What they didn't notice: the heavier prompt added ~250ms of "thinking" latency
to every reply. On a live phone call that's the difference between a snappy
agent and one that feels laggy — but it's invisible in a single manual test,
because the agent still completes the goal.

This is exactly the class of regression SoundCheck exists to catch.

## Reproduce it

The `--latency-bias` flag adds a fixed per-reply penalty to the offline mock,
standing in for that degraded config — so this whole story runs deterministically
with no API keys:

```bash
# Baseline — the clean config (this is the committed baseline)
soundcheck run --persona personas/appointment_booking.yaml --offline \
  --out baseline.json

# Candidate — same agent, bloated prompt adds 250ms
soundcheck run --persona personas/appointment_booking.yaml --offline \
  --latency-bias 250 --out candidate.json

# The gate blocks it
soundcheck gate --baseline baselines/appointment_booking.json --report candidate.json
```

## What the gate says

```
GATE FAILED:
  - ttfa_ms_p50 regressed: 295.2 -> 545.2 ms (+85%, tolerance +20%)
  - ttfa_ms_p95 regressed: 401.8 -> 651.8 ms (+62%, tolerance +20%)
```

Exit code `1` — in CI, the build goes red and the change never merges.

## What the reviewer sees on the pull request

The Action posts this comment automatically:

| Metric | Baseline | This run | Δ | |
|---|---:|---:|---:|:--:|
| ttfa_ms_p50 | 295.2 | 545.2 | +85% | ❌ |
| ttfa_ms_p95 | 401.8 | 651.8 | +62% | ❌ |
| turn_ms_p50 | 1560.5 | 1810.5 | +16% | ✅ |
| turn_ms_p95 | 1606.7 | 1856.7 | +16% | ✅ |
| goal_completed | True | True | — | ✅ |

**GATE FAILED** — `ttfa_ms_p50` and `ttfa_ms_p95` regressed past the +20% tolerance.

## The point

Note the last row: **`goal_completed` is still `True`.** The agent still did its
job — which is precisely why a manual test would have waved this change through.
SoundCheck fails the build on the metrics a human skim misses, and shows the
reviewer *exactly* what got worse, before a customer ever hears it.

> The `--latency-bias` knob is an honest simulation of a degraded config so this
> demo is reproducible offline. Against a real agent (`ELEVENLABS_API_KEY` +
> `--agent-id`), the same gate compares real before/after timing — the mechanism
> is identical; only the source of the numbers changes.
