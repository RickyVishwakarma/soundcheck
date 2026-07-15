"""Offline pipeline: persona -> mock transport -> metrics -> gate."""

import copy

from soundcheck import gate, runner
from soundcheck.personas import load_persona
from soundcheck.session import MockAgentTransport

PERSONA = "personas/appointment_booking.yaml"


def _report(seed: int = 11) -> dict:
    return runner.run(load_persona(PERSONA), MockAgentTransport(seed=seed))


def test_run_is_deterministic_for_a_seed():
    a, b = _report(), _report()
    assert a["turns"] == b["turns"]
    assert a["metrics"] == b["metrics"]


def test_mock_agent_completes_the_booking_goal():
    m = _report()["metrics"]
    assert m["goal_completed"] is True
    assert m["turn_count"] == 4
    assert m["ttfa_ms_p95"] > 0


def test_gate_passes_against_itself():
    r = _report()
    assert gate.compare(r, r) == []


def test_gate_catches_latency_regression():
    base = _report()
    slow = copy.deepcopy(base)
    slow["metrics"]["ttfa_ms_p95"] = base["metrics"]["ttfa_ms_p95"] * 2
    failures = gate.compare(base, slow)
    assert any("ttfa_ms_p95" in f for f in failures)


def test_gate_catches_goal_regression():
    base = _report()
    broken = copy.deepcopy(base)
    broken["metrics"]["goal_completed"] = False
    failures = gate.compare(base, broken)
    assert any("goal_completed" in f for f in failures)
