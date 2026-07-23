"""Concurrent suite execution: isolation, bounding, and failure containment."""

import threading
import time

import pytest

from soundcheck import suite as suite_mod
from soundcheck.personas import load_persona
from soundcheck.session import AgentReply, MockAgentTransport

PERSONAS = ["personas/appointment_booking.yaml", "personas/impatient_refund.yaml"]


def _cases(repeat=1):
    return [suite_mod.SuiteCase(load_persona(p), repeat=repeat) for p in PERSONAS]


def test_every_case_and_repeat_runs():
    result = suite_mod.run_suite(_cases(repeat=3), lambda: MockAgentTransport(), concurrency=4)
    assert result["summary"]["total"] == 6           # 2 personas x 3 repeats
    assert result["summary"]["ok"] == 6
    assert {r["attempt"] for r in result["runs"]} == {1, 2, 3}


def test_concurrency_is_bounded():
    """Never more calls in flight than the platform's concurrent-call cap."""
    live = 0
    peak = 0
    lock = threading.Lock()

    class SlowTransport(MockAgentTransport):
        def send(self, utterance, *, barge_in_after_ms=None) -> AgentReply:
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.02)
            try:
                return super().send(utterance, barge_in_after_ms=barge_in_after_ms)
            finally:
                with lock:
                    live -= 1

    suite_mod.run_suite(_cases(repeat=4), SlowTransport, concurrency=2)
    assert peak <= 2


def test_a_failing_run_does_not_sink_the_suite():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:            # first call blows up
            class Broken(MockAgentTransport):
                def start(self):
                    raise RuntimeError("connection refused")
            return Broken()
        return MockAgentTransport()

    result = suite_mod.run_suite(_cases(repeat=2), flaky, concurrency=2)
    assert result["summary"]["errors"] == 1
    assert result["summary"]["ok"] == 3          # the rest still completed
    broken = [r for r in result["runs"] if r["status"] == "error"][0]
    assert "connection refused" in broken["error"]


def test_transport_factory_is_called_per_run_not_shared():
    made = []

    def factory():
        t = MockAgentTransport(seed=len(made))
        made.append(t)
        return t

    suite_mod.run_suite(_cases(repeat=3), factory, concurrency=3)
    assert len(made) == 6
    assert len({id(t) for t in made}) == 6      # every run got its own transport


def test_flakiness_spread_is_reported_across_repeats():
    # Different seeds per run -> genuinely different latencies to spread over.
    counter = iter(range(100))
    result = suite_mod.run_suite(
        _cases(repeat=3), lambda: MockAgentTransport(seed=next(counter)), concurrency=3
    )
    flak = result["summary"]["flakiness"]
    assert flak, "repeats should produce a spread"
    for stats in flak.values():
        assert stats["max"] >= stats["min"]
        assert stats["spread_pct"] is not None


def test_empty_suite_is_rejected():
    with pytest.raises(ValueError):
        suite_mod.run_suite([], MockAgentTransport)


def test_results_are_ordered_regardless_of_completion():
    result = suite_mod.run_suite(_cases(repeat=2), MockAgentTransport, concurrency=4)
    keys = [(r["persona"], r["attempt"]) for r in result["runs"]]
    assert keys == sorted(keys)
