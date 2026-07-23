"""Real audio, not timing proxies.

The Agents WebSocket streams base64 PCM. Decoding it lets us measure what the
caller actually *heard* — how many milliseconds of speech the agent produced,
and how much of it landed on top of the caller after a barge-in — rather than
inferring everything from event arrival times.

Deliberately dependency-free: 16-bit mono PCM is just bytes, and duration is
arithmetic. `wave` (stdlib) writes the recordings.
"""

from __future__ import annotations

import base64
import struct
import wave
from pathlib import Path

# ElevenLabs Agents default output format: pcm_16000, 16-bit signed mono.
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # bytes per sample


def pcm_duration_ms(num_bytes: int, sample_rate: int = SAMPLE_RATE) -> float:
    """Milliseconds of audio in a 16-bit mono PCM buffer of `num_bytes`."""
    if num_bytes <= 0:
        return 0.0
    return (num_bytes / SAMPLE_WIDTH) / sample_rate * 1000.0


def decode_chunk(audio_base_64: str) -> bytes:
    """Decode one `audio` event's payload; tolerate padding issues."""
    if not audio_base_64:
        return b""
    try:
        return base64.b64decode(audio_base_64)
    except (ValueError, TypeError):
        return b""


def rms(pcm: bytes) -> float:
    """Root-mean-square amplitude (0..32767). Loudness, for silence checks."""
    count = len(pcm) // SAMPLE_WIDTH
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", pcm[: count * SAMPLE_WIDTH])
    return (sum(s * s for s in samples) / count) ** 0.5


class AudioCapture:
    """Accumulates an agent turn's PCM so it can be measured and replayed."""

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self._chunks: list[bytes] = []
        self._bytes_after_mark = 0
        self._marked = False

    def add(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._chunks.append(pcm)
        if self._marked:
            self._bytes_after_mark += len(pcm)

    def mark(self) -> None:
        """Start counting audio from here — called the instant we barge in."""
        self._marked = True

    @property
    def total_bytes(self) -> int:
        return sum(len(c) for c in self._chunks)

    @property
    def speech_ms(self) -> float:
        """Milliseconds of audio the agent actually produced this turn."""
        return round(pcm_duration_ms(self.total_bytes, self.sample_rate), 1)

    @property
    def talkover_ms(self) -> float:
        """Milliseconds of agent audio delivered *after* the caller barged in.

        This is the honest version of "it talked over me": real audio the
        caller heard on top of their own speech, not wall-clock latency.
        """
        return round(pcm_duration_ms(self._bytes_after_mark, self.sample_rate), 1)

    @property
    def rms(self) -> float:
        return round(rms(b"".join(self._chunks)), 1)

    def write_wav(self, path: str | Path) -> Path:
        """Save the turn as a playable WAV — the recording a reviewer listens to."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(SAMPLE_WIDTH)
            w.setframerate(self.sample_rate)
            w.writeframes(b"".join(self._chunks))
        return p
