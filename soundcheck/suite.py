"""Run many callers at once.

One scenario at a time is fine for a demo and useless for a real test pass: a
suite of twenty callers against a live agent would take ten minutes serially.
This runs them on a bounded thread pool — bounded because voice platforms cap
concurrent calls (ElevenLabs' free tier allows four), so unbounded fan-out gets
you rate-limited rather than fast.

Threads, not asyncio: the transport is blocking socket I/O, and every run needs
its own WebSocket and its own RNG, so isolation-per-thread is the natural fit.
A failing run is captured and reported, never allowed to take down the suite.
"""

from __future__ import annotations

import statistics
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from . import __version__, runner
from .personas import Persona
from .session import AgentTransport

# Voice platforms cap simultaneous calls; four matches the ElevenLabs free tier.
DEFAULT_CONCURRENCY = 4


class SuiteCase:
    """One persona to run, optionally several times to expose flakiness."""

    def __init__(self, persona: Persona, repeat: int = 1) -> None:
        self.persona = persona
        self.repeat = max(1, repeat)


def _run_one(
    persona: Persona,
    make_transport: Callable[[], AgentTransport],
    attempt: int,
    on_event: Optional[Callable[[str, str], None]],
) -> dict:
    """Execute a single call. Never raises — failures become data."""
    started = time.monotonic()
    if on_event:
        on_event("started", persona.name)
    try:
        report = runner.run(persona, make_transport())
        return {
            "persona": persona.name,
            "attempt": attempt,
            "status": "ok",
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "report": report,
        }
    except Exception:
        return {
            "persona": persona.name,
            "attempt": attempt,
            "status": "error",
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "error": traceback.format_exc(limit=3),
        }
    finally:
        if on_event:
            on_event("finished", persona.name)


def _spread(values: list[float]) -> Optional[dict]:
    """Min/max/stdev of a metric across repeats — how flaky the agent is."""
    if len(values) < 2:
        return None
    return {
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "stdev": round(statistics.stdev(values), 1),
        "spread_pct": round((max(values) / min(values) - 1) * 100, 1) if min(values) else None,
    }


def run_suite(
    cases: Iterable[SuiteCase],
    make_transport: Callable[[], AgentTransport],
    concurrency: int = DEFAULT_CONCURRENCY,
    on_event: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """Run every case (and repeat) concurrently, bounded by `concurrency`.

    `make_transport` is a factory, not a transport: each call needs its own
    connection and its own seeded RNG, so sharing one would corrupt both.
    """
    jobs: list[tuple[Persona, int]] = []
    for case in cases:
        for attempt in range(1, case.repeat + 1):
            jobs.append((case.persona, attempt))

    if not jobs:
        raise ValueError("suite has no cases")

    concurrency = max(1, min(concurrency, len(jobs)))
    peak = 0
    live = 0
    lock = threading.Lock()

    def track(event: str, name: str) -> None:
        nonlocal live, peak
        with lock:
            if event == "started":
                live += 1
                peak = max(peak, live)
            else:
                live -= 1
        if on_event:
            on_event(event, name)

    wall_start = time.monotonic()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="sc") as pool:
        futures = [pool.submit(_run_one, p, make_transport, a, track) for p, a in jobs]
        for fut in as_completed(futures):
            results.append(fut.result())
    wall_ms = round((time.monotonic() - wall_start) * 1000, 1)

    # Stable output regardless of completion order.
    results.sort(key=lambda r: (r["persona"], r["attempt"]))
    sequential_ms = round(sum(r["duration_ms"] for r in results), 1)

    ok = [r for r in results if r["status"] == "ok"]
    ttfa = [r["report"]["metrics"]["ttfa_ms_p95"] for r in ok]
    goals = [r["report"]["metrics"]["goal_completed"] for r in ok]

    # Flakiness per persona: how much the same scenario varies run to run.
    flakiness: dict[str, dict] = {}
    for name in {r["persona"] for r in ok}:
        vals = [
            r["report"]["metrics"]["ttfa_ms_p95"] for r in ok if r["persona"] == name
        ]
        spread = _spread(vals)
        if spread:
            flakiness[name] = spread

    return {
        "soundcheck_version": __version__,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "concurrency": concurrency,
        "peak_parallel": peak,
        "wall_ms": wall_ms,
        "sequential_ms": sequential_ms,
        # Measured, not claimed: how much the pool actually saved. Meaningless
        # when the calls are instant (an unpaced mock), so it is reported None.
        "speedup": round(sequential_ms / wall_ms, 2) if wall_ms >= 1.0 else None,
        "runs": results,
        "summary": {
            "total": len(results),
            "ok": len(ok),
            "errors": len(results) - len(ok),
            "goal_completed": sum(1 for g in goals if g),
            "goal_failed": sum(1 for g in goals if g is False),
            "ttfa_ms_p95_worst": round(max(ttfa), 1) if ttfa else None,
            "flakiness": flakiness,
        },
    }
