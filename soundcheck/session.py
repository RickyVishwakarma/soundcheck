"""Agent transports.

One protocol, two implementations: a deterministic offline mock (CI, demos, and
metric-pipeline development) and the live ElevenLabs Agents transport. Everything
downstream — personas, metrics, evals, gate — is transport-agnostic.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Protocol


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
    """Live transport against an ElevenLabs Agents conversation (Week 2).

    Planned implementation: open the Agents WebSocket, stream the persona
    utterance as TTS audio (so the agent hears a caller, not text), and measure
    TTFA from the first agent audio chunk — not the first text token, which is
    the number that actually matters on a phone call.
    """

    def __init__(self, agent_id: str, api_key: str) -> None:
        self.agent_id = agent_id
        self.api_key = api_key

    def start(self) -> None:
        raise NotImplementedError("Week 2: ElevenLabs Agents WebSocket transport")

    def send(self, utterance: str) -> AgentReply:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
