"""SoundCheck API — the engine, over HTTP.

Wraps the same runner/metrics/gate the CLI uses, so the hosted product and the
CI tool can never disagree about what a regression is.

Key decisions:
- **Bring your own key.** A live run takes the caller's ElevenLabs credentials
  for that request only; they are never written to the database or logs.
- **Demo mode needs no auth and no key** — it drives the deterministic mock
  agent, so anyone can see a real gate verdict in one click.
- Runs execute in a background thread and are polled; a voice test takes tens
  of seconds, which is far too long to hold a request open.
"""

from __future__ import annotations

import threading
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from soundcheck import gate, runner
from soundcheck import judge as judge_mod
from soundcheck.personas import Persona, Turn
from soundcheck.report import markdown_delta
from soundcheck.session import ElevenLabsTransport, MockAgentTransport

from . import store

PERSONA_DIR = Path(__file__).resolve().parent.parent / "personas"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.init()
    yield


app = FastAPI(
    title="SoundCheck API",
    version="0.3.0",
    description="Reliability testing for voice agents.",
    lifespan=lifespan,
)

# The dashboard is served from another origin (Vercel) in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- models


class PersonaTurn(BaseModel):
    say: str
    behavior: Optional[str] = None


class PersonaSpec(BaseModel):
    name: str
    goal: str = ""
    opening: str
    turns: list[PersonaTurn] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    mode: Literal["demo", "live"] = "demo"
    # Either name a bundled persona or supply one inline.
    persona_name: Optional[str] = None
    persona: Optional[PersonaSpec] = None
    # Live mode only. Never persisted.
    agent_id: Optional[str] = None
    api_key: Optional[str] = None
    # Offline only: simulate a degraded agent config.
    latency_bias_ms: float = 0.0


class RunAccepted(BaseModel):
    id: str
    status: str


# --------------------------------------------------------------------------- helpers


def _load_bundled(name: str) -> PersonaSpec:
    path = PERSONA_DIR / f"{name}.yaml"
    if not path.is_file():
        raise HTTPException(404, f"unknown persona {name!r}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PersonaSpec(
        name=raw["name"],
        goal=raw.get("goal", ""),
        opening=raw["opening"],
        turns=[PersonaTurn(**t) for t in raw.get("turns", [])],
        success_criteria=raw.get("success_criteria", {}).get("any_agent_reply_contains", []),
    )


def _to_persona(spec: PersonaSpec) -> Persona:
    return Persona(
        name=spec.name,
        goal=spec.goal,
        opening=spec.opening,
        turns=[Turn(say=t.say, behavior=t.behavior) for t in spec.turns],
        success_any=[s.lower() for s in spec.success_criteria],
    )


def _execute(run_id: str, spec: PersonaSpec, req: RunRequest) -> None:
    """Run in a worker thread, then gate against this persona's last report."""
    try:
        store.mark_running(run_id)
        if req.mode == "live":
            transport = ElevenLabsTransport(agent_id=req.agent_id or "", api_key=req.api_key or "")
        else:
            transport = MockAgentTransport(latency_bias_ms=req.latency_bias_ms)

        # Heuristic judge: deterministic and keyless, so the hosted demo shows
        # quality scores without asking anyone for an Anthropic key.
        persona = _to_persona(spec)
        report = runner.run(
            persona, transport, judge=judge_mod.build("heuristic", persona.success_any)
        )
        # Auto-baseline: compare against the previous run of the same persona.
        baseline = store.latest_passed(spec.name, before_id=run_id)
        failures = gate.compare(baseline, report) if baseline else []
        store.finish_run(run_id, report, failures)
    except Exception:
        store.fail_run(run_id, traceback.format_exc(limit=3))


# --------------------------------------------------------------------------- routes


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": app.version}


@app.get("/api/personas")
def list_personas() -> list[dict]:
    out = []
    for p in sorted(PERSONA_DIR.glob("*.yaml")):
        spec = _load_bundled(p.stem)
        out.append(
            {
                "name": spec.name,
                "goal": spec.goal,
                "turns": len(spec.turns) + 1,
                "behaviors": sorted({t.behavior for t in spec.turns if t.behavior}),
            }
        )
    return out


@app.post("/api/runs", response_model=RunAccepted, status_code=202)
def start_run(req: RunRequest) -> RunAccepted:
    if req.persona is not None:
        spec = req.persona
    elif req.persona_name:
        spec = _load_bundled(req.persona_name)
    else:
        raise HTTPException(422, "supply persona_name or persona")

    if req.mode == "live" and not (req.agent_id and req.api_key):
        raise HTTPException(422, "live mode needs agent_id and api_key")

    run_id = store.create_run(persona=spec.name, mode=req.mode)
    threading.Thread(target=_execute, args=(run_id, spec, req), daemon=True).start()
    return RunAccepted(id=run_id, status="queued")


@app.get("/api/runs")
def list_runs(limit: int = 50) -> list[dict]:
    return store.list_runs(limit=limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@app.get("/api/runs/{run_id}/delta")
def get_delta(run_id: str) -> dict:
    """Markdown delta vs the previous run — the PR comment, over HTTP."""
    run = store.get_run(run_id)
    if not run or not run.get("report"):
        raise HTTPException(404, "run not found or not finished")
    baseline = store.latest_passed(run["persona"], before_id=run_id)
    if not baseline:
        return {"markdown": "_No earlier run of this persona to compare against._"}
    return {"markdown": markdown_delta(baseline, run["report"])}
