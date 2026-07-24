"""Persistence.

SQLite via the stdlib so the API deploys anywhere Python does; swapping in
Postgres is this one module.

Tenancy rule: every read and write that touches tenant data takes `owner` as a
required argument and filters on it. There is deliberately no "get run by id"
that skips the owner check — that shape is how cross-tenant leaks happen.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent / "soundcheck.db"
_lock = threading.Lock()

# The unauthenticated public demo writes here, so anyone can try the product
# without an account and never sees another tenant's data.
DEMO_OWNER = "demo"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id           TEXT PRIMARY KEY,
    owner        TEXT NOT NULL DEFAULT 'demo',
    persona      TEXT NOT NULL,
    mode         TEXT NOT NULL,              -- demo | live
    status       TEXT NOT NULL,              -- queued | running | passed | failed | error
    created_at   TEXT NOT NULL,
    finished_at  TEXT,
    report_json  TEXT,
    failures_json TEXT,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_owner_created ON runs(owner, created_at DESC);

-- Caller scripts saved from the UI, so a tenant builds a scenario library
-- instead of editing YAML on disk.
CREATE TABLE IF NOT EXISTS scenarios (
    id         TEXT PRIMARY KEY,
    owner      TEXT NOT NULL,
    name       TEXT NOT NULL,
    spec_json  TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner, name)
);

-- Saved agents. The agent id is not a secret and is stored plainly; API keys
-- are deliberately NOT stored — they are supplied per run and never persisted.
CREATE TABLE IF NOT EXISTS agents (
    id         TEXT PRIMARY KEY,
    owner      TEXT NOT NULL,
    label      TEXT NOT NULL,
    agent_id   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner, label)
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ----------------------------------------------------------------------- users


def create_user(email: str, password_hash: str) -> Optional[dict]:
    """None when the email is taken — the caller turns that into a 409."""
    user_id = _uid("usr")
    try:
        with _lock, _conn() as c:
            c.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (?,?,?,?)",
                (user_id, email.lower().strip(), password_hash, _now()),
            )
    except sqlite3.IntegrityError:
        return None
    return {"id": user_id, "email": email.lower().strip()}


def get_user_by_email(email: str) -> Optional[dict]:
    with _lock, _conn() as c:
        r = c.execute(
            "SELECT * FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()
    return dict(r) if r else None


# ------------------------------------------------------------------------ runs


def create_run(persona: str, mode: str, owner: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO runs (id, owner, persona, mode, status, created_at)"
            " VALUES (?,?,?,?,'queued',?)",
            (run_id, owner, persona, mode, _now()),
        )
    return run_id


def mark_running(run_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))


def finish_run(run_id: str, report: dict, failures: list[str]) -> None:
    status = "failed" if failures else "passed"
    with _lock, _conn() as c:
        c.execute(
            "UPDATE runs SET status=?, finished_at=?, report_json=?, failures_json=?"
            " WHERE id=?",
            (status, _now(), json.dumps(report), json.dumps(failures), run_id),
        )


def fail_run(run_id: str, error: str) -> None:
    with _lock, _conn() as c:
        c.execute(
            "UPDATE runs SET status='error', finished_at=?, error=? WHERE id=?",
            (_now(), error, run_id),
        )


def _row_to_dict(r: sqlite3.Row, include_report: bool) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": r["id"],
        "persona": r["persona"],
        "mode": r["mode"],
        "status": r["status"],
        "created_at": r["created_at"],
        "finished_at": r["finished_at"],
        "error": r["error"],
    }
    d["failures"] = json.loads(r["failures_json"]) if r["failures_json"] else []
    report = json.loads(r["report_json"]) if r["report_json"] else None
    d["metrics"] = report["metrics"] if report else None
    if include_report:
        d["report"] = report
    return d


def get_run(run_id: str, owner: str) -> Optional[dict]:
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id=? AND owner=?", (run_id, owner)).fetchone()
    return _row_to_dict(r, include_report=True) if r else None


def list_runs(owner: str, limit: int = 50) -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT * FROM runs WHERE owner=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (owner, limit),
        ).fetchall()
    return [_row_to_dict(r, include_report=False) for r in rows]


def latest_passed(persona: str, owner: str, before_id: str | None = None) -> Optional[dict]:
    """Most recent finished run of this persona — the auto-baseline."""
    q = "SELECT * FROM runs WHERE owner=? AND persona=? AND report_json IS NOT NULL"
    params: list[Any] = [owner, persona]
    if before_id:
        q += " AND id != ?"
        params.append(before_id)
    q += " ORDER BY created_at DESC, rowid DESC LIMIT 1"
    with _lock, _conn() as c:
        r = c.execute(q, params).fetchone()
    return json.loads(r["report_json"]) if r else None


def trend(owner: str, persona: str, limit: int = 30) -> list[dict]:
    """Oldest-first metric history for charting drift over time."""
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT id, created_at, status, report_json FROM runs"
            " WHERE owner=? AND persona=? AND report_json IS NOT NULL"
            " ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (owner, persona, limit),
        ).fetchall()
    out = []
    for r in reversed(rows):
        m = json.loads(r["report_json"])["metrics"]
        out.append(
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "status": r["status"],
                "ttfa_ms_p95": m.get("ttfa_ms_p95"),
                "turn_ms_p95": m.get("turn_ms_p95"),
                "talkover_ms_p95": m.get("talkover_ms_p95"),
                "goal_completed": m.get("goal_completed"),
            }
        )
    return out


# ------------------------------------------------------------------- scenarios


def create_scenario(owner: str, name: str, spec: dict) -> Optional[dict]:
    sid = _uid("scn")
    try:
        with _lock, _conn() as c:
            c.execute(
                "INSERT INTO scenarios (id, owner, name, spec_json, created_at)"
                " VALUES (?,?,?,?,?)",
                (sid, owner, name, json.dumps(spec), _now()),
            )
    except sqlite3.IntegrityError:
        return None
    return {"id": sid, "name": name, "spec": spec}


def list_scenarios(owner: str) -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT * FROM scenarios WHERE owner=? ORDER BY created_at DESC", (owner,)
        ).fetchall()
    return [
        {"id": r["id"], "name": r["name"], "spec": json.loads(r["spec_json"]),
         "created_at": r["created_at"]}
        for r in rows
    ]


def get_scenario(owner: str, name: str) -> Optional[dict]:
    with _lock, _conn() as c:
        r = c.execute(
            "SELECT * FROM scenarios WHERE owner=? AND name=?", (owner, name)
        ).fetchone()
    return json.loads(r["spec_json"]) if r else None


def delete_scenario(owner: str, scenario_id: str) -> bool:
    with _lock, _conn() as c:
        cur = c.execute(
            "DELETE FROM scenarios WHERE owner=? AND id=?", (owner, scenario_id)
        )
    return cur.rowcount > 0


# ---------------------------------------------------------------------- agents


def create_agent(owner: str, label: str, agent_id: str) -> Optional[dict]:
    aid = _uid("agt")
    try:
        with _lock, _conn() as c:
            c.execute(
                "INSERT INTO agents (id, owner, label, agent_id, created_at)"
                " VALUES (?,?,?,?,?)",
                (aid, owner, label, agent_id, _now()),
            )
    except sqlite3.IntegrityError:
        return None
    return {"id": aid, "label": label, "agent_id": agent_id}


def list_agents(owner: str) -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT * FROM agents WHERE owner=? ORDER BY created_at DESC", (owner,)
        ).fetchall()
    return [
        {"id": r["id"], "label": r["label"], "agent_id": r["agent_id"],
         "created_at": r["created_at"]}
        for r in rows
    ]


def delete_agent(owner: str, agent_row_id: str) -> bool:
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM agents WHERE owner=? AND id=?", (owner, agent_row_id))
    return cur.rowcount > 0
