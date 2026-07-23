"""Run persistence.

SQLite via the stdlib: the server owns a queue of test runs and their reports,
and a run is small (a JSON blob plus status). Keeping it dependency-free means
the API deploys anywhere Python does; swapping in Postgres later is one module.
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

SCHEMA = """
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


def create_run(persona: str, mode: str, owner: str = "demo") -> str:
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
    failures = json.loads(r["failures_json"]) if r["failures_json"] else []
    d["failures"] = failures
    report = json.loads(r["report_json"]) if r["report_json"] else None
    # The list view only needs headline numbers, not every turn.
    d["metrics"] = report["metrics"] if report else None
    if include_report:
        d["report"] = report
    return d


def get_run(run_id: str, owner: str = "demo") -> Optional[dict]:
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id=? AND owner=?", (run_id, owner)).fetchone()
    return _row_to_dict(r, include_report=True) if r else None


def list_runs(owner: str = "demo", limit: int = 50) -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT * FROM runs WHERE owner=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (owner, limit),
        ).fetchall()
    return [_row_to_dict(r, include_report=False) for r in rows]


def latest_passed(persona: str, owner: str = "demo", before_id: str | None = None) -> Optional[dict]:
    """Most recent successful run for a persona — used as the auto-baseline."""
    q = "SELECT * FROM runs WHERE owner=? AND persona=? AND report_json IS NOT NULL"
    params: list[Any] = [owner, persona]
    if before_id:
        q += " AND id != ?"
        params.append(before_id)
    q += " ORDER BY created_at DESC, rowid DESC LIMIT 1"
    with _lock, _conn() as c:
        r = c.execute(q, params).fetchone()
    return json.loads(r["report_json"]) if r else None
