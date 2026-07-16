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


@dataclass
class AgentReply:
    text: str
    ttfa_ms: float   # time to first audio/token from end of user utterance
    total_ms: float  # full reply duration


class AgentTransport(Protocol):
    def start(self) -> None: ...
    def send(self, utterance: str) -> AgentReply: ...
    def close(self) -> None: ...


class MockAgentTransport:
    """Deterministic scripted agent with seeded latencies.

    Exists so the whole pipeline runs with zero external services: replies are
    keyword-based, latencies come from a seeded RNG, so a given persona always
    produces byte-identical reports — which is what makes the regression gate
    testable in CI for free.
    """

    def __init__(self, seed: int = 11) -> None:
        self._rng = random.Random(seed)

    def start(self) -> None:
        pass

    def send(self, utterance: str) -> AgentReply:
        lowered = utterance.lower()
        if any(w in lowered for w in ("book", "appointment", "schedule")):
            text = "I can help with that. What day works for you?"
        elif any(w in lowered for w in ("tuesday", "10am", "works")):
            text = "You're booked for Tuesday at 10am — confirmed."
        elif any(w in lowered for w in ("cost", "price", "how much")):
            text = "A standard cleaning is 1500 rupees."
        else:
            text = "Could you tell me a bit more so I can help?"
        ttfa = self._rng.uniform(180, 420)
        total = ttfa + self._rng.uniform(600, 1800)
        return AgentReply(text=text, ttfa_ms=round(ttfa, 1), total_ms=round(total, 1))

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

    def send(self, utterance: str) -> AgentReply:
        if self._ws is None:
            raise RuntimeError("transport not started; call start() first")
        self._ws.send(json.dumps({"type": "user_message", "text": utterance}))
        return self._consume_turn(self._recv, self._send_pong, _now_ms)

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
    ) -> AgentReply:
        """Fold a stream of server frames into one timed AgentReply.

        `recv` returns a parsed frame, or None when the read idled out (which,
        once audio has started, is how we detect the turn ended). Kept free of
        socket/JSON concerns so it can be driven by a scripted list in tests.
        """
        t0 = now_ms()
        ttfa_ms: Optional[float] = None
        last_audio_ms: Optional[float] = None
        text_parts: list[str] = []

        while True:
            frame = recv()
            now = now_ms()

            if frame is None:
                if last_audio_ms is not None:
                    break  # audio started, then went quiet -> turn over
                if now - t0 >= self.turn_timeout_ms:
                    break  # agent never responded
                continue

            ftype = frame.get("type")
            if ftype == "audio":
                if ttfa_ms is None:
                    ttfa_ms = now - t0
                last_audio_ms = now
                if frame.get("audio_event", {}).get("is_final"):
                    break
            elif ftype == "agent_response":
                text = frame.get("agent_response_event", {}).get("agent_response")
                if text:
                    text_parts.append(text)
            elif ftype == "ping":
                on_ping(frame.get("ping_event", {}).get("event_id"))
            # interruption / user_transcript / metadata frames: not turn-ending

        total_ms = (last_audio_ms - t0) if last_audio_ms is not None else (now_ms() - t0)
        return AgentReply(
            text=" ".join(text_parts) or "(no agent text)",
            ttfa_ms=round(ttfa_ms or 0.0, 1),
            total_ms=round(total_ms, 1),
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
