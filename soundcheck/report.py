"""Human-facing outputs — the PR-comment markdown delta.

The gate decides pass/fail; this renders *why* in a form a reviewer reads in
five seconds on the pull request. Same comparison logic as the gate (it calls
it), so the comment and the exit code can never disagree.
"""

from __future__ import annotations

from . import gate as gate_mod


def markdown_delta(
    baseline: dict, report: dict, tolerance: float = gate_mod.LATENCY_TOLERANCE
) -> str:
    base_m, new_m = baseline["metrics"], report["metrics"]
    failures = gate_mod.compare(baseline, report, tolerance)
    # gate failure strings start with the offending metric key.
    failed = {f.split(" ")[0] for f in failures}

    lines = [
        f"## 🔊 SoundCheck — `{report.get('persona', 'agent')}` reliability delta",
        "",
        "| Metric | Baseline | This run | Δ | |",
        "|---|---:|---:|---:|:--:|",
    ]
    for key in gate_mod.LATENCY_KEYS:
        base_v, new_v = base_m.get(key), new_m.get(key)
        if base_v is None and new_v is None:
            continue
        if base_v and new_v is not None:
            delta = f"{(new_v / base_v - 1) * 100:+.0f}%"
        else:
            delta = "—"
        mark = "❌" if key in failed else "✅"
        lines.append(f"| {key} | {base_v} | {new_v} | {delta} | {mark} |")

    base_goal, new_goal = base_m.get("goal_completed"), new_m.get("goal_completed")
    if base_goal is not None or new_goal is not None:
        mark = "❌" if "goal_completed" in failed else "✅"
        lines.append(f"| goal_completed | {base_goal} | {new_goal} | — | {mark} |")

    lines.append("")
    if failures:
        lines.append("**GATE FAILED** — this change makes the agent worse:")
        lines.extend(f"- {f}" for f in failures)
    else:
        lines.append(
            f"**GATE PASSED** — no regressions beyond the +{tolerance * 100:.0f}% tolerance."
        )
    return "\n".join(lines)
