"""Caller personas.

A persona is a simulated caller: an opening line, a sequence of turns (optionally
tagged with adversarial behaviors), and success criteria that define what a
"handled" call looks like. Scripted personas are YAML; LLM-driven personas
(goal + temperament -> generated turns) land in Week 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

BEHAVIORS = {"offtopic", "interrupt", "silence", "language_switch"}


@dataclass
class Turn:
    say: str
    behavior: str | None = None


@dataclass
class Persona:
    name: str
    goal: str
    opening: str
    turns: list[Turn] = field(default_factory=list)
    # Call counts as successful if any agent reply contains one of these.
    success_any: list[str] = field(default_factory=list)


def load_persona(path: str | Path) -> Persona:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    turns = []
    for t in raw.get("turns", []):
        behavior = t.get("behavior")
        if behavior is not None and behavior not in BEHAVIORS:
            raise ValueError(f"unknown behavior {behavior!r} in {path}")
        turns.append(Turn(say=t["say"], behavior=behavior))
    return Persona(
        name=raw["name"],
        goal=raw["goal"],
        opening=raw["opening"],
        turns=turns,
        success_any=[s.lower() for s in raw.get("success_criteria", {}).get("any_agent_reply_contains", [])],
    )
