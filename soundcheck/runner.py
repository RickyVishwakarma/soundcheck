"""Drive one persona against one transport and produce a report."""

from __future__ import annotations

from datetime import datetime, timezone

from . import __version__, metrics
from .personas import Persona
from .session import AgentTransport


# How long the caller lets the agent talk before barging in on `interrupt` turns.
BARGE_IN_AFTER_MS = 400.0


def run(persona: Persona, transport: AgentTransport) -> dict:
    transport.start()
    try:
        turns = []
        utterances = [persona.opening] + [t.say for t in persona.turns]
        behaviors = [None] + [t.behavior for t in persona.turns]
        for utterance, behavior in zip(utterances, behaviors):
            barge = BARGE_IN_AFTER_MS if behavior == "interrupt" else None
            reply = transport.send(utterance, barge_in_after_ms=barge)
            turns.append(
                {
                    "user": utterance,
                    "behavior": behavior,
                    "agent": reply.text,
                    "ttfa_ms": reply.ttfa_ms,
                    "total_ms": reply.total_ms,
                    "recovery_ms": reply.recovery_ms,
                }
            )
    finally:
        transport.close()

    return {
        "soundcheck_version": __version__,
        "persona": persona.name,
        "goal": persona.goal,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "turns": turns,
        "metrics": metrics.compute(turns, persona.success_any),
    }
