"""The regression gate — the reason the rest of the harness exists.

Compares a fresh report against a committed baseline and returns human-readable
failures. Policy: goal completion may never regress; latency percentiles may
drift up to a tolerance before the gate trips.
"""

from __future__ import annotations

# Max allowed relative increase on latency percentile metrics (0.20 == +20%).
LATENCY_TOLERANCE = 0.20
LATENCY_KEYS = (
    "ttfa_ms_p50",
    "ttfa_ms_p95",
    "turn_ms_p50",
    "turn_ms_p95",
    "recovery_ms_p95",
    # Real audio the caller heard on top of their own speech — the metric a
    # text-only eval pipeline cannot produce.
    "talkover_ms_p95",
)

# Judge scores, 1-5, higher is better — compared in the opposite direction.
QUALITY_KEYS = ("instruction_following", "tone")


def compare(baseline: dict, report: dict, tolerance: float = LATENCY_TOLERANCE) -> list[str]:
    failures: list[str] = []
    base_m, new_m = baseline["metrics"], report["metrics"]

    if base_m.get("goal_completed") and not new_m.get("goal_completed"):
        failures.append("goal_completed regressed: baseline succeeded, this run did not")

    # A clean baseline that starts hallucinating is a hard failure, like goals.
    if new_m.get("hallucinated") and not base_m.get("hallucinated"):
        failures.append("hallucinated: baseline invented nothing, this run did")

    # Judge scores run 1-5 and higher is better, so the regression is a DROP —
    # the opposite direction from the latency keys above.
    for key in QUALITY_KEYS:
        base_v, new_v = base_m.get(key), new_m.get(key)
        if base_v is None or new_v is None:
            continue
        if new_v < base_v * (1 - tolerance):
            failures.append(
                f"{key} regressed: {base_v} -> {new_v} "
                f"({(new_v / base_v - 1) * 100:.0f}%, tolerance -{tolerance * 100:.0f}%)"
            )

    for key in LATENCY_KEYS:
        base_v, new_v = base_m.get(key), new_m.get(key)
        if not base_v or new_v is None:
            continue
        if new_v > base_v * (1 + tolerance):
            failures.append(
                f"{key} regressed: {base_v} -> {new_v} ms "
                f"(+{(new_v / base_v - 1) * 100:.0f}%, tolerance +{tolerance * 100:.0f}%)"
            )
    return failures
