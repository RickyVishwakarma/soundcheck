"""Agent transports.

One protocol, two implementations: a deterministic offline mock (CI, demos, and
metric-pipeline development) and the live ElevenLabs Agents transport. Everything
downstream — personas, metrics, evals, gate — is transport-agnostic.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .audio import SAMPLE_RATE, AudioCapture, decode_chunk


@dataclass
class AgentReply:
    text: str
    ttfa_ms: float   # time to first audio/token from end of user utterance
    total_ms: float  # full reply duration
    # Barge-in recovery: how long the agent kept talking after the caller
    # interrupted mid-reply. None when the turn had no interruption.
    recovery_ms: Optional[float] = None
    # Measured from the decoded PCM stream, not from event timings:
    speech_ms: Optional[float] = None    # audio the agent actually produced
    talkover_ms: Optional[float] = None  # audio delivered after a barge-in


class AgentTransport(Protocol):
    def start(self) -> None: ...
    def send(self, utterance: str, *, barge_in_after_ms: Optional[float] = None) -> AgentReply: ...
    def close(self) -> None: ...


# What the simulated caller says when barging in mid-reply.
BARGE_IN_TEXT = "Sorry — hold on, one second."


class MockAgentTransport:
    """Deterministic scripted agent with seeded latencies.

    Exists so the whole pipeline runs with zero external services: replies are
    keyword-based, latencies come from a seeded RNG, so a given persona always
    produces byte-identical reports — which is what makes the regression gate
    testable in CI for free.
    """

    def __init__(self, seed: int = 11, latency_bias_ms: float = 0.0) -> None:
        self._rng = random.Random(seed)
        # A fixed penalty added to every reply's timing — stands in for a
        # degraded agent config (e.g. a bloated system prompt that adds
        # "thinking" latency). Lets a case study show the gate catching a
        # regression deterministically, without a live agent.
        self._bias = latency_bias_ms

    def start(self) -> None:
        pass

    def send(self, utterance: str, *, barge_in_after_ms: Optional[float] = None) -> AgentReply:
        lowered = utterance.lower()
        if any(w in lowered for w in ("book", "appointment", "schedule")):
            text = "I can help with that. What day works for you?"
        elif any(w in lowered for w in ("tuesday", "10am", "works")):
            text = "You're booked for Tuesday at 10am — confirmed."
        elif any(w in lowered for w in ("cost", "price", "how much")):
            text = "A standard cleaning is 1500 rupees."
        elif any(w in lowered for w in ("refund", "money back", "cancel")):
            text = "I understand. I can process that refund for you right now."
        else:
            text = "Could you tell me a bit more so I can help?"
        ttfa = self._rng.uniform(180, 420) + self._bias
        total = ttfa + self._rng.uniform(600, 1800)
        recovery = None
        if barge_in_after_ms is not None:
            # A well-behaved agent stops quickly after a barge-in; the mock's
            # recovery time is seeded like its latencies so runs stay identical.
            # A heavier config is also slower to notice the barge-in, so the
            # bias feeds recovery too.
            recovery = round(self._rng.uniform(150, 500) + self._bias, 1)
            total = round(barge_in_after_ms + recovery + self._rng.uniform(200, 600), 1)
        # Synthesize the PCM a real agent would have streamed, so speech/talkover
        # are computed by the same arithmetic as the live path rather than faked.
        # Speaking rate ~14 chars/sec; 16-bit mono @ 16kHz.
        speech_ms = len(text) / 14.0 * 1000.0
        capture = AudioCapture()
        capture.add(b"\x00\x00" * int(SAMPLE_RATE * speech_ms / 1000.0))
        talkover = None
        if barge_in_after_ms is not None:
            capture.mark()
            # Audio still in flight when the caller cut in.
            capture.add(b"\x00\x00" * int(SAMPLE_RATE * (recovery or 0.0) / 1000.0))
            talkover = capture.talkover_ms
        return AgentReply(
            text=text,
            ttfa_ms=round(ttfa, 1),
            total_ms=round(total, 1),
            recovery_ms=recovery,
            speech_ms=capture.speech_ms,
            talkover_ms=talkover,
        )

    def close(self) -> None:
        pass


class ElevenLabsTransport:
    """Live transport against an ElevenLabs Agents conversation.

    Drives the Agents WebSocket programmatically: sends the persona utterance as
    a `user_message`, then measures TTFA from the first `audio` event — not the
    first text token, which is the number that actually matters on a phone call.

    The turn-consumption logic lives in the pure `_consume_turn` method so the
    timing math is unit-testable without a live socket or an API key; `send`
    just wires the real WebSocket into it.
    """

    WS_URL = "wss://api.elevenlabs.io/v1/convai/conversation?agent_id={agent_id}"

    def __init__(
        self,
        agent_id: str,
        api_key: str,
        *,
        quiet_ms: float = 2500.0,
        turn_timeout_ms: float = 30000.0,
        connect_timeout_ms: float = 15000.0,
        audio_dir: Optional[str] = None,
    ) -> None:
        if not agent_id:
            raise ValueError("agent_id is required for the live ElevenLabs transport")
        self.agent_id = agent_id
        self.api_key = api_key
        # Idle gap (no audio) that marks the end of an agent turn.
        self.quiet_ms = quiet_ms
        # Hard ceiling on waiting for a turn (agent never responds).
        self.turn_timeout_ms = turn_timeout_ms
        self.connect_timeout_ms = connect_timeout_ms
        # When set, each agent turn is saved as a playable WAV for review.
        self.audio_dir = audio_dir
        self._turn_index = 0
        self._ws = None

    def start(self) -> None:
        try:
            import websocket  # websocket-client; only needed for the live path
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise RuntimeError(
                "the live transport needs websocket-client: pip install websocket-client"
            ) from exc

        url = self.WS_URL.format(agent_id=self.agent_id)
        header = [f"xi-api-key: {self.api_key}"] if self.api_key else []
        self._ws = websocket.create_connection(
            url, header=header, timeout=self.quiet_ms / 1000.0
        )
        self._ws.send(json.dumps({"type": "conversation_initiation_client_data"}))
        # Drain until the server confirms the conversation is live, answering
        # pings so the connection is not dropped while we wait.
        deadline = time.monotonic() + self.connect_timeout_ms / 1000.0
        while time.monotonic() < deadline:
            frame = self._recv()
            if frame is None:
                continue
            if frame.get("type") == "ping":
                self._send_pong(frame.get("ping_event", {}).get("event_id"))
            elif frame.get("type") == "conversation_initiation_metadata":
                return
        raise TimeoutError("ElevenLabs agent did not initiate the conversation in time")

    def send(self, utterance: str, *, barge_in_after_ms: Optional[float] = None) -> AgentReply:
        if self._ws is None:
            raise RuntimeError("transport not started; call start() first")
        self._ws.send(json.dumps({"type": "user_message", "text": utterance}))
        return self._consume_turn(
            self._recv,
            self._send_pong,
            _now_ms,
            barge_in_after_ms=barge_in_after_ms,
            barge_in=lambda: self._ws.send(
                json.dumps({"type": "user_message", "text": BARGE_IN_TEXT})
            ),
        )

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    # --- pure, testable core --------------------------------------------------

    def _consume_turn(
        self,
        recv: Callable[[], Optional[dict]],
        on_ping: Callable[[Optional[int]], None],
        now_ms: Callable[[], float],
        *,
        barge_in_after_ms: Optional[float] = None,
        barge_in: Optional[Callable[[], None]] = None,
    ) -> AgentReply:
        """Fold a stream of server frames into one timed AgentReply.

        `recv` returns a parsed frame, or None when the read idled out (which,
        once audio has started, is how we detect the turn ended). Kept free of
        socket/JSON concerns so it can be driven by a scripted list in tests.

        If `barge_in_after_ms` is set, `barge_in()` fires once the agent has
        been speaking that long; recovery_ms is then how much longer agent
        audio kept arriving — the number a caller experiences as "it wouldn't
        stop talking over me".
        """
        t0 = now_ms()
        ttfa_ms: Optional[float] = None
        last_audio_ms: Optional[float] = None
        barged_at_ms: Optional[float] = None
        text_parts: list[str] = []
        capture = AudioCapture()

        while True:
            frame = recv()
            now = now_ms()

            if (
                barge_in_after_ms is not None
                and barge_in is not None
                and barged_at_ms is None
                and ttfa_ms is not None
                and now - (t0 + ttfa_ms) >= barge_in_after_ms
            ):
                barge_in()
                barged_at_ms = now
                # Everything the agent sends from here is talk-over.
                capture.mark()

            if frame is None:
                if last_audio_ms is not None:
                    break  # audio started, then went quiet -> turn over
                if now - t0 >= self.turn_timeout_ms:
                    break  # agent never responded
                continue

            # The server sends keepalive pings every ~2s, so recv() rarely
            # idles out on a live socket. End-of-turn has to be judged by how
            # long it has been since *audio*, not since any frame at all.
            if last_audio_ms is not None and now - last_audio_ms >= self.quiet_ms:
                break
            if last_audio_ms is None and now - t0 >= self.turn_timeout_ms:
                break

            ftype = frame.get("type")
            if ftype == "audio":
                if ttfa_ms is None:
                    ttfa_ms = now - t0
                last_audio_ms = now
                capture.add(decode_chunk(frame.get("audio_event", {}).get("audio_base_64", "")))
                if frame.get("audio_event", {}).get("is_final"):
                    break
            elif ftype == "agent_response":
                text = frame.get("agent_response_event", {}).get("agent_response")
                if text:
                    text_parts.append(text)
            elif ftype == "ping":
                on_ping(frame.get("ping_event", {}).get("event_id"))
            elif ftype == "interruption" and barged_at_ms is not None:
                break  # server confirmed the barge-in cut the agent off
            # user_transcript / metadata frames: not turn-ending

        total_ms = (last_audio_ms - t0) if last_audio_ms is not None else (now_ms() - t0)
        recovery_ms: Optional[float] = None
        if barged_at_ms is not None:
            # Audio that kept arriving after the interruption; 0 if it stopped dead.
            recovery_ms = round(max((last_audio_ms or barged_at_ms) - barged_at_ms, 0.0), 1)
        if self.audio_dir and capture.total_bytes:
            self._turn_index += 1
            capture.write_wav(f"{self.audio_dir}/turn_{self._turn_index:02d}.wav")

        return AgentReply(
            text=" ".join(text_parts) or "(no agent text)",
            ttfa_ms=round(ttfa_ms or 0.0, 1),
            total_ms=round(total_ms, 1),
            recovery_ms=recovery_ms,
            speech_ms=capture.speech_ms,
            talkover_ms=capture.talkover_ms if barged_at_ms is not None else None,
        )

    # --- socket glue ----------------------------------------------------------

    def _recv(self) -> Optional[dict]:
        import websocket  # local import keeps offline users dependency-free

        try:
            raw = self._ws.recv()
        except websocket.WebSocketTimeoutException:
            return None
        if not raw:
            return None
        return json.loads(raw)

    def _send_pong(self, event_id: Optional[int]) -> None:
        if self._ws is not None:
            self._ws.send(json.dumps({"type": "pong", "event_id": event_id}))


def _now_ms() -> float:
    return time.monotonic() * 1000.0
