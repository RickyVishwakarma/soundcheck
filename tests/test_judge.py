"""Transcript judging: the judge decides goal completion, and the gate
compares quality scores in the opposite direction from latency."""

import copy

import pytest

from soundcheck import gate, judge as judge_mod, metrics, runner
from soundcheck.personas import load_persona
from soundcheck.session import MockAgentTransport

PERSONA = "personas/appointment_booking.yaml"


class StubJudge:
    """Stands in for the LLM so tests need no key and no network."""

    name = "stub"

    def __init__(self, **overrides):
        self.result = {
            "task_completed": True,
            "task_completed_reason": "the agent confirmed the booking",
            "hallucinated": False,
            "hallucination_detail": "",
            "instruction_following": 5,
            "tone": 4,
            **overrides,
        }
        self.calls = []

    def score(self, goal, turns):
        self.calls.append((goal, turns))
        return {"judge": self.name, **self.result}


def _run(judge=None):
    return runner.run(load_persona(PERSONA), MockAgentTransport(seed=11), judge=judge)


def test_no_judge_leaves_the_report_unjudged():
    report = _run(judge=None)
    assert report["judge"] is None
    assert report["metrics"]["tone"] is None
    assert report["metrics"]["goal_completed"] is True   # keyword fallback still works


def test_judge_verdict_becomes_metrics():
    stub = StubJudge()
    m = _run(judge=stub)["metrics"]
    assert m["instruction_following"] == 5
    assert m["tone"] == 4
    assert m["hallucinated"] is False
    assert stub.calls, "judge should have been called"


def test_judge_overrides_keyword_goal_detection():
    """The point of the judge: recognise success the keywords would miss."""
    turns = [{"user": "book me in", "agent": "Your appointment is set for Tuesday.",
              "behavior": None, "ttfa_ms": 1, "total_ms": 2,
              "recovery_ms": None, "speech_ms": 10, "talkover_ms": None}]

    # Keyword check looks for "booked"/"confirmed" — this phrasing has neither.
    without = metrics.compute(turns, ["booked", "confirmed"], None)
    assert without["goal_completed"] is False

    verdict = {"judge": "stub", "task_completed": True, "hallucinated": False,
               "instruction_following": 5, "tone": 5}
    with_judge = metrics.compute(turns, ["booked", "confirmed"], verdict)
    assert with_judge["goal_completed"] is True


def test_a_broken_judge_never_loses_the_run():
    class Exploding:
        name = "boom"

        def score(self, goal, turns):
            raise RuntimeError("api down")

    report = _run(judge=Exploding())
    assert "api down" in report["judge"]["error"]
    assert report["metrics"]["ttfa_ms_p95"] > 0          # timing data survives
    assert report["metrics"]["goal_completed"] is True   # falls back to keywords


def test_gate_catches_a_quality_drop_not_a_rise():
    base = _run(judge=StubJudge(instruction_following=5, tone=5))

    worse = copy.deepcopy(base)
    worse["metrics"]["instruction_following"] = 2
    failures = gate.compare(base, worse)
    assert any("instruction_following" in f for f in failures)

    better = copy.deepcopy(base)
    better["metrics"]["tone"] = 5
    better["metrics"]["instruction_following"] = 5
    assert gate.compare(base, better) == []   # scores are inverse to latency


def test_gate_catches_new_hallucination():
    base = _run(judge=StubJudge(hallucinated=False))
    lying = copy.deepcopy(base)
    lying["metrics"]["hallucinated"] = True
    assert any("hallucinated" in f for f in gate.compare(base, lying))


def test_heuristic_judge_is_deterministic_and_keyless():
    j = judge_mod.HeuristicJudge(["booked", "confirmed"])
    turns = _run()["turns"]
    assert j.score("book it", turns) == j.score("book it", turns)
    assert j.score("book it", turns)["task_completed"] is True


def test_build_selects_and_validates():
    assert judge_mod.build("none") is None
    assert isinstance(judge_mod.build("heuristic", []), judge_mod.HeuristicJudge)
    assert isinstance(judge_mod.build("claude"), judge_mod.ClaudeJudge)
    with pytest.raises(ValueError):
        judge_mod.build("gpt")


def test_claude_judge_targets_the_current_model():
    assert judge_mod.ClaudeJudge().model == "claude-opus-4-8"
    # The schema must stay strict or structured outputs will not validate.
    assert judge_mod.RESULT_SCHEMA["additionalProperties"] is False
