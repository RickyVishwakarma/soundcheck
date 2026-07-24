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
from pydantic import BaseModel, EmailStr, Field

from soundcheck import gate, runner
from soundcheck import judge as judge_mod
from soundcheck.personas import Persona, Turn
from soundcheck.report import markdown_delta
from soundcheck.session import ElevenLabsTransport, MockAgentTransport

from . import auth, store

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
    """Resolve the tenant for this request.

    No token means the shared public-demo tenant rather than a 401, so the
    landing page works for a first-time visitor with no account.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return store.DEMO_OWNER
    claims = auth.read_token(authorization.split(" ", 1)[1].strip())
    if not claims:
        raise HTTPException(401, "session expired or invalid — sign in again")
    return claims["sub"]


def require_account(owner: str = Depends(current_owner)) -> str:
    """For routes that must not fall back to the demo tenant."""
    if owner == store.DEMO_OWNER:
        raise HTTPException(401, "sign in to use this")
    return owner


# --------------------------------------------------------------------- models


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class Session(BaseModel):
    token: str
    email: str


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


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": app.version}


# --- auth -------------------------------------------------------------------


@app.post("/api/auth/signup", response_model=Session, status_code=201)
def signup(body: Credentials) -> Session:
    user = store.create_user(body.email, auth.hash_password(body.password))
    if user is None:
        raise HTTPException(409, "that email already has an account")
    return Session(token=auth.issue_token(user["id"], user["email"]), email=user["email"])


@app.post("/api/auth/login", response_model=Session)
def login(body: Credentials) -> Session:
    user = store.get_user_by_email(body.email)
    # Same message either way — distinguishing them tells an attacker which
    # emails are registered.
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "wrong email or password")
    return Session(token=auth.issue_token(user["id"], user["email"]), email=user["email"])


@app.get("/api/auth/me")
def me(authorization: Optional[str] = Header(default=None)) -> dict:
    owner = current_owner(authorization)
    if owner == store.DEMO_OWNER:
        return {"authenticated": False, "email": None}
    claims = auth.read_token(authorization.split(" ", 1)[1].strip())
    return {"authenticated": True, "email": (claims or {}).get("email")}


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
