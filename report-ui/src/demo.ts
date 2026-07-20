import type { Payload } from "./types";

/** Rendered when no data is injected (`npm run dev`, or opening the raw
 *  template): a realistic failing run so the design is honest about how
 *  regressions look. Values match the committed impatient_refund baseline. */
export const DEMO: Payload = {
  tolerance: 0.2,
  failures: [
    "recovery_ms_p95 regressed: 327.7 -> 416.0 ms (+27%, tolerance +20%)",
  ],
  baseline: {
    soundcheck_version: "0.2.0",
    persona: "impatient_refund",
    goal: "Get a refund for a cancelled service, while talking over the agent",
    generated_at: "2026-07-16T09:00:00+00:00",
    turns: [],
    metrics: {
      turn_count: 4,
      ttfa_ms_p50: 309.9,
      ttfa_ms_p95: 401.8,
      turn_ms_p50: 1300.7,
      turn_ms_p95: 1560.3,
      recovery_ms_p95: 327.7,
      goal_completed: true,
    },
  },
  report: {
    soundcheck_version: "0.2.0",
    persona: "impatient_refund",
    goal: "Get a refund for a cancelled service, while talking over the agent",
    generated_at: "2026-07-16T12:34:56+00:00",
    turns: [
      {
        user: "Hi, I need a refund for the appointment you cancelled on me.",
        behavior: null,
        agent: "I understand. I can process that refund for you right now.",
        ttfa_ms: 274.4,
        total_ms: 1116.8,
        recovery_ms: null,
      },
      {
        user: "No listen, I don't want to rebook - I want my money back.",
        behavior: "interrupt",
        agent: "I understand. I can process that refund for you right now.",
        ttfa_ms: 309.3,
        total_ms: 1211.6,
        recovery_ms: 416.0,
      },
      {
        user: "How long until it reaches my account?",
        behavior: null,
        agent: "Could you tell me a bit more so I can help?",
        ttfa_ms: 254.9,
        total_ms: 1693.1,
        recovery_ms: null,
      },
      {
        user: "Fine. Please process the refund.",
        behavior: "interrupt",
        agent: "I understand. I can process that refund for you right now.",
        ttfa_ms: 230.1,
        total_ms: 1022.0,
        recovery_ms: 388.2,
      },
    ],
    metrics: {
      turn_count: 4,
      ttfa_ms_p50: 264.7,
      ttfa_ms_p95: 309.3,
      turn_ms_p50: 1164.2,
      turn_ms_p95: 1693.1,
      recovery_ms_p95: 416.0,
      goal_completed: true,
    },
  },
};
