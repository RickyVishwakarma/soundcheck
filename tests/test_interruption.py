"""Barge-in injection and the recovery metric, offline and at the turn-logic level."""

import copy

from soundcheck import gate, runner
from soundcheck.personas import load_persona
from soundcheck.session import ElevenLabsTransport, MockAgentTransport

PERSONA = "personas/impatient_refund.yaml"


def _report(seed: int = 11) -> dict:
    return runner.run(load_persona(PERSONA), MockAgentTransport(seed=seed))


def test_interrupt_turns_produce_recovery_and_others_do_not():
    turns = _report()["turns"]
    by_behavior = {t["behavior"]: t for t in turns}
    assert by_behavior["interrupt"]["recovery_ms"] is not None
    assert by_behavior[None]["recovery_ms"] is None


def test_recovery_metric_is_deterministic_and_gated():
    a, b = _report(), _report()
    assert a["metrics"]["recovery_ms_p95"] == b["metrics"]["recovery_ms_p95"]
    assert a["metrics"]["recovery_ms_p95"] > 0

    slow = copy.deepcopy(a)
    slow["metrics"]["recovery_ms_p95"] = a["metrics"]["recovery_ms_p95"] * 2
    failures = gate.compare(a, slow)
    assert any("recovery_ms_p95" in f for f in failures)


def test_live_turn_logic_measures_recovery_after_barge_in():
    """Scripted frames: agent starts talking, we barge in, it talks a bit more."""
    t = ElevenLabsTransport(agent_id="agent_x", api_key="k")
    barges = []
    frames = [
        {"type": "audio", "audio_event": {"audio_base_64": "aa"}},  # reply starts
        {"type": "audio", "audio_event": {"audio_base_64": "bb"}},  # still talking -> barge fires
        {"type": "audio", "audio_event": {"audio_base_64": "cc"}},  # talked over us 200ms
        {"type": "interruption", "interruption_event": {"event_id": 1}},
    ]
    # t0, 1st audio (ttfa=100), 2nd audio (500ms into speech -> barge), 3rd audio, interruption
    times = [1000, 1100, 1600, 1800, 1900]
    frame_iter, time_iter = iter(frames), iter(times)

    reply = t._consume_turn(
        lambda: next(frame_iter),
        on_ping=lambda _id: None,
        now_ms=lambda: next(time_iter),
        barge_in_after_ms=400.0,
        barge_in=lambda: barges.append(True),
    )

    assert barges == [True]                 # barge-in fired exactly once
    assert reply.ttfa_ms == 100.0
    assert reply.recovery_ms == 200.0       # audio at 1800 minus barge at 1600
