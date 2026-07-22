"""The --latency-bias knob that powers the case study.

A fixed penalty must push a run past the gate while leaving goal completion
intact — the whole point of the case study is a regression a manual test misses.
"""

from soundcheck import gate, runner
from soundcheck.personas import load_persona
from soundcheck.session import MockAgentTransport

PERSONA = "personas/appointment_booking.yaml"


def _run(bias: float = 0.0) -> dict:
    return runner.run(load_persona(PERSONA), MockAgentTransport(seed=11, latency_bias_ms=bias))


def test_bias_raises_latency_by_the_penalty():
    clean = _run(0.0)["metrics"]
    biased = _run(250.0)["metrics"]
    assert round(biased["ttfa_ms_p95"] - clean["ttfa_ms_p95"], 1) == 250.0


def test_bias_trips_the_gate_but_keeps_goal_completion():
    clean = _run(0.0)
    biased = _run(250.0)
    failures = gate.compare(clean, biased)
    assert any("ttfa_ms" in f for f in failures)          # latency regressed
    assert biased["metrics"]["goal_completed"] is True    # ...but the job still got done
