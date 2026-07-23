"""Transcript judging — did the agent actually do its job, and do it well?

Keyword matching answers "did the reply contain the word 'booked'", which is
brittle: an agent that says "your appointment is set for Tuesday" completed the
task and fails the check. A judge reads the transcript and decides.

Two implementations behind one protocol:

- `HeuristicJudge` — deterministic, no network, no key. This is what CI runs, so
  the gate stays free and flake-less.
- `ClaudeJudge` — reads the conversation and scores task success, hallucination,
  instruction-following and tone. Opt-in, used when a key is present.

The gate treats judge scores like any other metric: task success may not
regress, and the 1-5 scores may drift down only within tolerance.
"""

from __future__ import annotations

from typing import Optional, Protocol

# Scores are 1-5; the gate compares them like latency percentiles (higher is
# better here, so a *drop* past tolerance is the regression).
SCORE_KEYS = ("instruction_following", "tone")

JUDGE_MODEL = "claude-opus-4-8"

# Structured output contract — the judge must return exactly this shape.
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_completed": {
            "type": "boolean",
            "description": "Did the agent accomplish the caller's stated goal?",
        },
        "task_completed_reason": {
            "type": "string",
            "description": "One sentence citing the turn that settles it.",
        },
        "hallucinated": {
            "type": "boolean",
            "description": "Did the agent state something it could not know or that contradicts the conversation?",
        },
        "hallucination_detail": {
            "type": "string",
            "description": "What was invented, or empty string if nothing was.",
        },
        "instruction_following": {
            "type": "integer",
            "enum": [1, 2, 3, 4, 5],
            "description": "5 = answered exactly what was asked every turn; 1 = ignored the caller.",
        },
        "tone": {
            "type": "integer",
            "enum": [1, 2, 3, 4, 5],
            "description": "5 = natural and appropriate for a phone call; 1 = robotic or rude.",
        },
    },
    "required": [
        "task_completed",
        "task_completed_reason",
        "hallucinated",
        "hallucination_detail",
        "instruction_following",
        "tone",
    ],
    "additionalProperties": False,
}

SYSTEM = """You grade transcripts of phone calls between a simulated caller and \
an AI voice agent. You are strict but fair: judge only what the transcript shows.

The caller is a test script, so its turns may be terse or adversarial — grade the
AGENT, never the caller. A turn tagged `interrupt` means the caller talked over
the agent mid-sentence; the agent's reply may look clipped as a result, and that
is not itself a fault.

Task completion means the caller's goal was actually accomplished, regardless of
the exact words used: "your appointment is set for Tuesday at 10" completes a
booking just as well as "you're booked". Do not reward an agent that merely
promises to do the thing later."""


class Judge(Protocol):
    name: str

    def score(self, goal: str, turns: list[dict]) -> dict: ...


def _transcript(turns: list[dict]) -> str:
    lines = []
    for i, t in enumerate(turns, 1):
        tag = f" [{t['behavior']}]" if t.get("behavior") else ""
        lines.append(f"{i}. CALLER{tag}: {t['user']}")
        lines.append(f"   AGENT: {t['agent']}")
    return "\n".join(lines)


class HeuristicJudge:
    """Deterministic scoring — the CI default.

    Keyword-based task detection (the original behaviour), plus cheap proxies
    for the qualitative scores so offline reports have the same shape as judged
    ones and the gate does not have to special-case a missing judge.
    """

    name = "heuristic"

    def __init__(self, success_any: Optional[list[str]] = None) -> None:
        self.success_any = [s.lower() for s in (success_any or [])]

    def score(self, goal: str, turns: list[dict]) -> dict:
        replies = " ".join(t["agent"].lower() for t in turns)
        completed = (
            any(s in replies for s in self.success_any) if self.success_any else False
        )
        # An agent that keeps asking the caller to repeat themselves is not
        # following along; that is the one signal available without a model.
        confused = sum(
            1 for t in turns if "tell me a bit more" in t["agent"].lower()
        )
        following = max(1, 5 - confused * 2)
        return {
            "judge": self.name,
            "task_completed": completed,
            "task_completed_reason": (
                "matched success keyword" if completed else "no success keyword in replies"
            ),
            "hallucinated": False,  # not detectable without a model
            "hallucination_detail": "",
            "instruction_following": following,
            "tone": 3,  # neutral placeholder; only the LLM judge grades tone
        }


class ClaudeJudge:
    """LLM judge. Opt-in — needs ANTHROPIC_API_KEY."""

    name = "claude"

    def __init__(self, model: str = JUDGE_MODEL, api_key: Optional[str] = None) -> None:
        self.model = model
        self._api_key = api_key

    def score(self, goal: str, turns: list[dict]) -> dict:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "the Claude judge needs the SDK: pip install 'soundcheck[judge]'"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key) if self._api_key else anthropic.Anthropic()
        prompt = (
            f"The caller's goal was: {goal}\n\n"
            f"Transcript:\n{_transcript(turns)}\n\n"
            "Grade the agent."
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": RESULT_SCHEMA},
            },
            messages=[{"role": "user", "content": prompt}],
        )
        import json

        text = "".join(b.text for b in message.content if b.type == "text")
        result = json.loads(text)
        result["judge"] = self.name
        return result


def build(kind: str, success_any: Optional[list[str]] = None) -> Optional[Judge]:
    """`none` disables judging entirely; the report simply omits the block."""
    if kind == "none":
        return None
    if kind == "heuristic":
        return HeuristicJudge(success_any)
    if kind == "claude":
        return ClaudeJudge()
    raise ValueError(f"unknown judge {kind!r} (none | heuristic | claude)")
