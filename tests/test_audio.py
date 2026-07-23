"""Audio decoding and the metrics derived from real PCM, not event timings."""

import base64
import struct
import wave

from soundcheck import runner
from soundcheck.audio import SAMPLE_RATE, AudioCapture, decode_chunk, pcm_duration_ms, rms
from soundcheck.personas import load_persona
from soundcheck.session import ElevenLabsTransport, MockAgentTransport


def _pcm(ms: float, amplitude: int = 0) -> bytes:
    """`ms` of 16-bit mono PCM at the agent's sample rate."""
    n = int(SAMPLE_RATE * ms / 1000.0)
    return struct.pack(f"<{n}h", *([amplitude] * n))


def test_duration_is_derived_from_byte_count():
    # 1 second of 16kHz 16-bit mono = 32000 bytes
    assert pcm_duration_ms(32_000) == 1000.0
    assert pcm_duration_ms(0) == 0.0
    assert round(pcm_duration_ms(len(_pcm(250))), 1) == 250.0


def test_decode_chunk_survives_garbage():
    assert decode_chunk("") == b""
    assert decode_chunk("!!!not base64!!!") == b""
    payload = base64.b64encode(b"\x01\x02\x03\x04").decode()
    assert decode_chunk(payload) == b"\x01\x02\x03\x04"


def test_capture_measures_speech_and_talkover_from_the_mark():
    cap = AudioCapture()
    cap.add(_pcm(500))       # agent speaks 500ms
    cap.mark()               # caller barges in here
    cap.add(_pcm(200))       # agent keeps going 200ms
    assert cap.speech_ms == 700.0
    assert cap.talkover_ms == 200.0   # only audio after the barge-in counts


def test_rms_distinguishes_silence_from_signal():
    assert rms(_pcm(50, amplitude=0)) == 0.0
    assert rms(_pcm(50, amplitude=8000)) > 7000


def test_capture_writes_a_playable_wav(tmp_path):
    cap = AudioCapture()
    cap.add(_pcm(120, amplitude=1000))
    out = cap.write_wav(tmp_path / "turn.wav")
    with wave.open(str(out), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == SAMPLE_RATE
        assert round(w.getnframes() / SAMPLE_RATE * 1000) == 120


def test_live_turn_derives_speech_from_decoded_audio():
    """Two 100ms chunks arrive; speech_ms must come from the bytes."""
    t = ElevenLabsTransport(agent_id="a", api_key="k")
    chunk = base64.b64encode(_pcm(100)).decode()
    frames = [
        {"type": "audio", "audio_event": {"audio_base_64": chunk}},
        {"type": "audio", "audio_event": {"audio_base_64": chunk, "is_final": True}},
    ]
    times = [0, 100, 200]
    fi, ti = iter(frames), iter(times)
    reply = t._consume_turn(lambda: next(fi), on_ping=lambda _: None, now_ms=lambda: next(ti))
    assert reply.speech_ms == 200.0     # 2 x 100ms of real PCM
    assert reply.talkover_ms is None    # no barge-in this turn


def test_mock_reports_audio_metrics_too():
    report = runner.run(
        load_persona("personas/impatient_refund.yaml"), MockAgentTransport(seed=11)
    )
    m = report["metrics"]
    assert m["speech_ms_total"] > 0
    assert m["talkover_ms_p95"] is not None      # persona has interrupt turns
    interrupted = [t for t in report["turns"] if t["behavior"] == "interrupt"]
    assert all(t["talkover_ms"] > 0 for t in interrupted)
