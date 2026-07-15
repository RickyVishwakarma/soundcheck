# SoundCheck — 4-week build plan

Goal: an artifact strong enough to lead an ElevenLabs Full-Stack Engineer
application ("showcase solving impressively hard problems"), doubling as a
portfolio piece for Maxim AI (evals), Portkey (observability), and Smallest.ai
(voice). Ship in public: small commits, honest README, demo video at the end.

## Week 1 — Offline harness, end to end (this repo's scaffold)

- [ ] `AgentTransport` protocol + `MockAgentTransport` with seeded latencies
- [ ] Persona YAML schema + scripted persona runner
- [ ] Metrics: TTFA, per-turn latency p50/p95, goal completion (keyword criteria)
- [ ] Regression gate: baseline JSON vs report JSON, thresholds, exit codes
- [ ] CI: pytest + an actual gate run on every push (the harness gates itself)
- [ ] 3 example personas: appointment booking, angry refund, topic-switcher

**Exit criterion:** `cli run --offline` → `cli gate` passes green in GitHub Actions.

## Week 2 — Live ElevenLabs transport + adversarial behavior

- [ ] `ElevenLabsTransport`: Agents WebSocket, real audio timing (TTFA measured
      from first audio chunk, not first text token)
- [ ] Interruption injection: barge-in mid-reply, measure recovery (does the agent
      stop, resume, or double-talk?)
- [ ] LLM-driven persona engine: goal + temperament → generated turns
- [ ] LLM-judge evals (faithfulness, task success) with deterministic local fallback
- [ ] File SDK issues/PRs for any rough edges hit (contribution track — see below)

**Exit criterion:** same persona produces comparable reports on mock vs live agent.

## Week 3 — Dashboard

- [ ] Next.js + TypeScript app in `dashboard/`: load report JSONs
- [ ] Trace tree per conversation (turns, timings, judge scores, audio events)
- [ ] Latency waterfall + run-over-run regression diff view
- [ ] Deploy on Vercel with bundled demo data (recruiters click, no setup)

**Exit criterion:** a public URL where a stranger understands a regression in 30s.

## Week 4 — Polish, proof, publish

- [ ] Case study in README: take a public agent config, introduce a plausible
      regression (e.g. bloated system prompt), show the gate catching it
- [ ] 90-second demo video (Loom): run → regress → gate fails → dashboard diff
- [ ] Write-up post (blog/X/LinkedIn), share in ElevenLabs Discord
- [ ] THEN apply: Full-Stack Engineer (lead with repo + video + merged PRs)

## Contribution track (parallel, ~2h/week)

- Weeks 1–2: while integrating, log every SDK/docs rough edge → issues with repros
- Weeks 2–3: land 1–2 PRs on elevenlabs-python / elevenlabs-js / examples repo
- Ongoing: active in their Discord; answer questions in the agents channel
- Watch for ElevenLabs-sponsored hackathons — enter with SoundCheck as the base

## Guardrails

- Lyzr interview prep and the Composio/Portkey/Maxim applications come FIRST each
  week; SoundCheck is the background project (~10-12 h/week).
- Do not apply to ElevenLabs before the demo video + at least one merged PR exist.
- Every README claim must be runnable by a stranger — same bar as Quantis.
