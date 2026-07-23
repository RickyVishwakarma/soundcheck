"""Every declared behavior must change execution.

`silence` and `language_switch` were accepted by the persona loader and then
silently ignored by the runner — a declared-but-dead feature. These tests pin
that each behavior reaches the transport.
"""

import pytest

from soundcheck import runner, session
from soundcheck.personas import BEHAVIORS, load_persona
from soundcheck.session import AgentReply, MockAgentTransport


class RecordingTransport(MockAgentTransport):
    """Captures the kwargs the runner passes for each turn."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls = []

    def send(self, utterance, *, barge_in_after_ms=None, silence_before_ms=None) -> AgentReply:
        self.calls.append(
            {
                "utterance": utterance,
                "barge_in_after_ms": barge_in_after_ms,
                "silence_before_ms": silence_before_ms,
            }
        )
        return super().send(
            utterance,
            barge_in_after_ms=barge_in_after_ms,
            silence_before_ms=silence_before_ms,
        )


def _calls(persona_path):
    t = RecordingTransport(seed=11)
    report = runner.run(load_persona(persona_path), t)
    return t.calls, report


def test_silence_turns_reach_the_transport():
    calls, report = _calls("personas/hesitant_caller.yaml")
    behaviors = [t["behavior"] for t in report["turns"]]

    for call, behavior in zip(calls, behaviors):
        if behavior == "silence":
            assert call["silence_before_ms"] == session.SILENCE_MS
        else:
            assert call["silence_before_ms"] is None

    assert behaviors.count("silence") == 2, "persona should exercise silence twice"


def test_language_switch_turns_are_delivered_verbatim():
    """The switch is in the utterance itself — it must not be mangled."""
    calls, report = _calls("personas/bilingual_caller.yaml")
    said = [c["utterance"] for c in calls]

    assert any("español" in s for s in said)
    assert any("नमस्ते" in s for s in said)
    # language_switch is not a timing behavior — no barge-in, no silence.
    for call, turn in zip(calls, report["turns"]):
        if turn["behavior"] == "language_switch":
            assert call["barge_in_after_ms"] is None
            assert call["silence_before_ms"] is None


def test_mock_answers_a_code_switching_caller():
    m = MockAgentTransport(seed=11)
    reply = m.send("Hola, ¿habla español?")
    assert "English" in reply.text          # acknowledges rather than ignoring


def test_silence_is_not_slept_when_unpaced():
    """Tests must stay instant — the pause only happens in paced demo runs."""
    import time

    m = MockAgentTransport(seed=11, pace=False)
    start = time.monotonic()
    m.send("hello", silence_before_ms=3000)
    assert (time.monotonic() - start) < 0.5


def test_every_declared_behavior_is_exercised_by_a_persona():
    """Guards against re-introducing a declared-but-dead behavior."""
    import pathlib

    import yaml

    seen = set()
    for path in pathlib.Path("personas").glob("*.yaml"):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for turn in raw.get("turns", []):
            if turn.get("behavior"):
                seen.add(turn["behavior"])

    assert seen == BEHAVIORS, f"behaviors with no persona coverage: {BEHAVIORS - seen}"


@pytest.mark.parametrize("persona", ["hesitant_caller", "bilingual_caller"])
def test_new_personas_are_deterministic(persona):
    a = runner.run(load_persona(f"personas/{persona}.yaml"), MockAgentTransport(seed=11))
    b = runner.run(load_persona(f"personas/{persona}.yaml"), MockAgentTransport(seed=11))
    assert a["metrics"] == b["metrics"]
