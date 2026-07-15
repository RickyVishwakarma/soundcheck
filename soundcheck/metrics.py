"""Metrics over a timed transcript.

Latency numbers are the caller-experienced kind: time-to-first-audio and total
turn latency, reported as p50/p95 because a voice agent that is usually fast but
occasionally hangs is a bad voice agent.
"""

from __future__ import annotations

import statistics


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    # quantiles() extrapolates past the observed range on small samples; a
    # latency percentile above the slowest observed turn would be a lie.
    qs = statistics.quantiles(values, n=100)
    return round(min(qs[min(int(pct) - 1, 98)], max(values)), 1)


def compute(turns: list[dict], success_any: list[str]) -> dict:
    ttfas = [t["ttfa_ms"] for t in turns]
    totals = [t["total_ms"] for t in turns]
    replies = " ".join(t["agent"].lower() for t in turns)
    return {
        "turn_count": len(turns),
        "ttfa_ms_p50": _pct(ttfas, 50),
        "ttfa_ms_p95": _pct(ttfas, 95),
        "turn_ms_p50": _pct(totals, 50),
        "turn_ms_p95": _pct(totals, 95),
        "goal_completed": any(s in replies for s in success_any) if success_any else None,
    }
