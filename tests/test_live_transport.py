"""Live-transport turn logic, exercised without a socket or API key.

`ElevenLabsTransport._consume_turn` is deliberately pure: it folds a stream of
server frames into one timed reply. Here we drive it with scripted frames and a
scripted clock, so the TTFA/turn-latency math and ping handling are verified in
CI for free — the same zero-dependency discipline as the offline pipeline.
"""

from soundcheck.session import ElevenLabsTransport


def _driver(frames, times):
    """Build (recv, now) callables from scripted frames and timestamps."""
    frame_iter = iter(frames)
    time_iter = iter(times)
    return (lambda: next(frame_iter)), (lambda: next(time_iter))


def _transport():
    # No start() / socket — we only exercise the pure core.
    return ElevenLabsTransport(agent_id="agent_x", api_key="k")


def test_ttfa_is_measured_from_first_audio_not_first_text():
    frames = [
        {"type": "agent_response", "agent_response_event": {"agent_response": "Hello there"}},
        {"type": "audio", "audio_event": {"audio_base_64": "aa"}},
        {"type": "audio", "audio_event": {"audio_base_64": "bb"}},
        None,  # idle read after audio -> turn is over
    ]
    # t0, after agent_response, after 1st audio, after 2nd audio, after idle
    times = [1000, 1050, 1200, 1400, 1600]
    recv, now = _driver(frames, times)

    reply = _transport()._consume_turn(recv, on_ping=lambda _id: None, now_ms=now)

    assert reply.ttfa_ms == 200.0          # 1200 - 1000: first *audio*, not the text at 1050
    assert reply.total_ms == 400.0         # last audio (1400) - t0 (1000)
    assert reply.text == "Hello there"


def test_ping_is_answered_and_final_audio_ends_the_turn():
    pings = []
    frames = [
        {"type": "ping", "ping_event": {"event_id": 7}},
        {"type": "audio", "audio_event": {"audio_base_64": "aa", "is_final": True}},
    ]
    times = [1000, 1010, 1300]  # t0, after ping, after final audio
    recv, now = _driver(frames, times)

    reply = _transport()._consume_turn(recv, on_ping=pings.append, now_ms=now)

    assert pings == [7]                     # we ponged the keepalive
    assert reply.ttfa_ms == 300.0
    assert reply.total_ms == 300.0          # is_final stops the turn immediately


def test_no_response_stops_at_turn_timeout():
    t = _transport()
    frames = [None, None, None]             # agent never emits audio
    times = [0, 10_000, 20_000, 40_000, 40_000]  # crosses the 30s ceiling
    recv, now = _driver(frames, times)

    reply = t._consume_turn(recv, on_ping=lambda _id: None, now_ms=now)

    assert reply.ttfa_ms == 0.0
    assert reply.text == "(no agent text)"
