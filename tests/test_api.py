"""The hosted API must produce the same verdicts as the CLI."""

import time

import pytest
from fastapi.testclient import TestClient

from server import store
from server.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Isolate each test from the developer's real run history.
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    store.init()
    with TestClient(app) as c:
        yield c


def _await_finish(client, run_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish")


def test_demo_run_needs_no_key_and_reports_metrics(client):
    r = client.post("/api/runs", json={"mode": "demo", "persona_name": "impatient_refund"})
    assert r.status_code == 202
    run = _await_finish(client, r.json()["id"])

    assert run["status"] == "passed"          # nothing to regress against yet
    m = run["metrics"]
    assert m["goal_completed"] is True
    assert m["talkover_ms_p95"] > 0           # audio metrics survive the round trip
    assert len(run["report"]["turns"]) == 4


def test_second_run_is_gated_against_the_first(client):
    first = client.post("/api/runs", json={"mode": "demo", "persona_name": "appointment_booking"})
    _await_finish(client, first.json()["id"])

    # Same persona, but the agent config now costs an extra 250ms per reply.
    second = client.post(
        "/api/runs",
        json={
            "mode": "demo",
            "persona_name": "appointment_booking",
            "latency_bias_ms": 250,
        },
    )
    run = _await_finish(client, second.json()["id"])

    assert run["status"] == "failed"
    assert any("ttfa_ms" in f for f in run["failures"])

    delta = client.get(f"/api/runs/{run['id']}/delta").json()["markdown"]
    assert "GATE FAILED" in delta


def test_live_mode_requires_credentials(client):
    r = client.post("/api/runs", json={"mode": "live", "persona_name": "appointment_booking"})
    assert r.status_code == 422


def test_unknown_persona_is_rejected(client):
    r = client.post("/api/runs", json={"mode": "demo", "persona_name": "nope"})
    assert r.status_code == 404


def test_custom_persona_can_be_supplied_inline(client):
    r = client.post(
        "/api/runs",
        json={
            "mode": "demo",
            "persona": {
                "name": "custom_caller",
                "goal": "book something",
                "opening": "I'd like to book an appointment",
                "turns": [{"say": "Tuesday 10am works", "behavior": "interrupt"}],
                "success_criteria": ["booked", "confirmed"],
            },
        },
    )
    run = _await_finish(client, r.json()["id"])
    assert run["report"]["persona"] == "custom_caller"
    assert run["metrics"]["goal_completed"] is True


def test_runs_are_listed_newest_first(client):
    for _ in range(2):
        rid = client.post(
            "/api/runs", json={"mode": "demo", "persona_name": "appointment_booking"}
        ).json()["id"]
        _await_finish(client, rid)
    runs = client.get("/api/runs").json()
    assert len(runs) == 2
    assert runs[0]["created_at"] >= runs[1]["created_at"]
    assert "report" not in runs[0]            # list view stays light
