"""SoundCheck API — the engine, over HTTP, multi-tenant.

Wraps the same runner/metrics/gate the CLI uses, so the hosted product and the
CI tool can never disagree about what a regression is.

Key decisions:
- **Bring your own key.** A live run takes the caller's ElevenLabs credentials
  for that request only; they are never written to the database or the logs.
- **The public demo needs no account** — it drives the deterministic mock agent
  under a shared `demo` tenant, so anyone can see a real gate verdict in one
  click without signing up, and never sees another tenant's data.
- **Owner comes from the token, never the body.** Every tenant-scoped call
  resolves the owner from the session, so a caller cannot request another
  tenant's runs by guessing an id.
- Runs execute in a background thread and are polled; a voice test takes tens
  of seconds, far too long to hold a request open.
"""

from __future__ import annotations

import threading
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from soundcheck import gate, runner
from soundcheck import judge as judge_mod
from soundcheck.personas import Persona, Turn
from soundcheck.report import markdown_delta
from soundcheck.session import ElevenLabsTransport, MockAgentTransport

from . import clerk_auth, store

PERSONA_DIR = Path(__file__).resolve().parent.parent / "personas"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.init()
    yield


app = FastAPI(
    title="SoundCheck API",
    version="0.4.0",
    description="Reliability testing for voice agents.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- identity


def current_owner(authorization: Optional[str] = Header(default=None)) -> str:
    """Resolve the tenant for this request from the Clerk session token.

    No token means the shared public-demo tenant rather than a 401, so the
    landing page works for a first-time visitor with no account. When a token
    *is* present it must verify — the Clerk user id becomes the tenant key.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return store.DEMO_OWNER
    user_id = clerk_auth.verify_token(authorization.split(" ", 1)[1].strip())
    if not user_id:
        raise HTTPException(401, "session expired or invalid — sign in again")
    return user_id


def require_account(owner: str = Depends(current_owner)) -> str:
    """For routes that must not fall back to the demo tenant."""
    if owner == store.DEMO_OWNER:
        raise HTTPException(401, "sign in to use this")
    return owner


# --------------------------------------------------------------------- models


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
    persona_name: Optional[str] = None      # bundled or a saved scenario
    persona: Optional[PersonaSpec] = None   # or supplied inline
    agent_id: Optional[str] = None
    api_key: Optional[str] = None           # live only; never persisted
    latency_bias_ms: float = 0.0


class RunAccepted(BaseModel):
    id: str
    status: str


class AgentIn(BaseModel):
    label: str
    agent_id: str


# --------------------------------------------------------------------- helpers


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


def _resolve_persona(req: RunRequest, owner: str) -> PersonaSpec:
    if req.persona is not None:
        return req.persona
    if not req.persona_name:
        raise HTTPException(422, "supply persona_name or persona")
    # A tenant's own scenario shadows a bundled one of the same name.
    saved = store.get_scenario(owner, req.persona_name)
    if saved:
        return PersonaSpec(**saved)
    return _load_bundled(req.persona_name)


def _to_persona(spec: PersonaSpec) -> Persona:
    return Persona(
        name=spec.name,
        goal=spec.goal,
        opening=spec.opening,
        turns=[Turn(say=t.say, behavior=t.behavior) for t in spec.turns],
        success_any=[s.lower() for s in spec.success_criteria],
    )


def _execute(run_id: str, spec: PersonaSpec, req: RunRequest, owner: str) -> None:
    """Run in a worker thread, then gate against this tenant's last report."""
    try:
        store.mark_running(run_id)
        if req.mode == "live":
            transport = ElevenLabsTransport(agent_id=req.agent_id or "", api_key=req.api_key or "")
        else:
            transport = MockAgentTransport(latency_bias_ms=req.latency_bias_ms)

        persona = _to_persona(spec)
        report = runner.run(
            persona, transport, judge=judge_mod.build("heuristic", persona.success_any)
        )
        baseline = store.latest_passed(spec.name, owner, before_id=run_id)
        failures = gate.compare(baseline, report) if baseline else []
        store.finish_run(run_id, report, failures)
    except Exception:
        store.fail_run(run_id, traceback.format_exc(limit=3))


# ---------------------------------------------------------------------- routes


@app.get("/")
def root() -> dict:
    """The API serves /api/* only — a bare 404 at the root is confusing when
    someone opens this URL by mistake, so point them at the docs and health."""
    return {
        "service": "SoundCheck API",
        "version": app.version,
        "docs": "/docs",
        "health": "/api/health",
        "note": "This is the API. The web app is the dashboard, served separately.",
    }


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": app.version}


# --- auth -------------------------------------------------------------------
# Sign-up, sign-in and session lifetime are Clerk's job. The backend only
# verifies the token it is handed (see `current_owner`), so there are no
# credential endpoints here — nothing to attack, and no password to store.


@app.get("/api/auth/me")
def me(owner: str = Depends(current_owner)) -> dict:
    """Whether this request is an authenticated tenant or the public demo."""
    return {
        "authenticated": owner != store.DEMO_OWNER,
        "owner": None if owner == store.DEMO_OWNER else owner,
        "clerk_configured": clerk_auth.is_configured(),
    }


# --- scenarios --------------------------------------------------------------


@app.get("/api/personas")
def list_personas(owner: str = Depends(current_owner)) -> list[dict]:
    """Bundled examples plus this tenant's saved scenarios."""
    out = []
    for p in sorted(PERSONA_DIR.glob("*.yaml")):
        spec = _load_bundled(p.stem)
        out.append(
            {
                "name": spec.name,
                "goal": spec.goal,
                "turns": len(spec.turns) + 1,
                "behaviors": sorted({t.behavior for t in spec.turns if t.behavior}),
                "source": "bundled",
            }
        )
    for s in store.list_scenarios(owner):
        spec = PersonaSpec(**s["spec"])
        out.append(
            {
                "id": s["id"],
                "name": spec.name,
                "goal": spec.goal,
                "turns": len(spec.turns) + 1,
                "behaviors": sorted({t.behavior for t in spec.turns if t.behavior}),
                "source": "saved",
            }
        )
    return out


@app.post("/api/scenarios", status_code=201)
def create_scenario(spec: PersonaSpec, owner: str = Depends(require_account)) -> dict:
    created = store.create_scenario(owner, spec.name, spec.model_dump())
    if created is None:
        raise HTTPException(409, f"you already have a scenario named {spec.name!r}")
    return created


@app.delete("/api/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str, owner: str = Depends(require_account)) -> None:
    if not store.delete_scenario(owner, scenario_id):
        raise HTTPException(404, "scenario not found")


# --- agents -----------------------------------------------------------------


@app.get("/api/agents")
def list_agents(owner: str = Depends(require_account)) -> list[dict]:
    return store.list_agents(owner)


@app.post("/api/agents", status_code=201)
def create_agent(body: AgentIn, owner: str = Depends(require_account)) -> dict:
    created = store.create_agent(owner, body.label, body.agent_id)
    if created is None:
        raise HTTPException(409, f"you already have an agent labelled {body.label!r}")
    return created


@app.delete("/api/agents/{agent_row_id}", status_code=204)
def delete_agent(agent_row_id: str, owner: str = Depends(require_account)) -> None:
    if not store.delete_agent(owner, agent_row_id):
        raise HTTPException(404, "agent not found")


# --- runs -------------------------------------------------------------------


@app.post("/api/runs", response_model=RunAccepted, status_code=202)
def start_run(req: RunRequest, owner: str = Depends(current_owner)) -> RunAccepted:
    spec = _resolve_persona(req, owner)
    if req.mode == "live" and not (req.agent_id and req.api_key):
        raise HTTPException(422, "live mode needs agent_id and api_key")

    run_id = store.create_run(persona=spec.name, mode=req.mode, owner=owner)
    threading.Thread(
        target=_execute, args=(run_id, spec, req, owner), daemon=True
    ).start()
    return RunAccepted(id=run_id, status="queued")


@app.get("/api/runs")
def list_runs(limit: int = 50, owner: str = Depends(current_owner)) -> list[dict]:
    return store.list_runs(owner, limit=limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, owner: str = Depends(current_owner)) -> dict:
    run = store.get_run(run_id, owner)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@app.get("/api/runs/{run_id}/delta")
def get_delta(run_id: str, owner: str = Depends(current_owner)) -> dict:
    """Markdown delta vs the previous run — the PR comment, over HTTP."""
    run = store.get_run(run_id, owner)
    if not run or not run.get("report"):
        raise HTTPException(404, "run not found or not finished")
    baseline = store.latest_passed(run["persona"], owner, before_id=run_id)
    if not baseline:
        return {"markdown": "_No earlier run of this scenario to compare against._"}
    return {"markdown": markdown_delta(baseline, run["report"])}


@app.get("/api/trends/{persona}")
def get_trend(persona: str, limit: int = 30, owner: str = Depends(current_owner)) -> list[dict]:
    """Metric history for one scenario, oldest first — drift over time."""
    return store.trend(owner, persona, limit=limit)
