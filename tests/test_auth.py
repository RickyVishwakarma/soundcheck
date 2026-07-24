"""Accounts and tenant isolation.

The isolation tests matter more than the auth ones: a SaaS that leaks one
customer's runs to another is worse than one with no accounts at all.
"""

import time

import pytest
from fastapi.testclient import TestClient

from server import auth, store
from server.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "auth.db")
    store.init()
    with TestClient(app) as c:
        yield c


def _signup(client, email="a@example.com", password="correct horse battery"):
    r = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _finish(client, run_id, headers, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}", headers=headers).json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


# --------------------------------------------------------------------- hashing


def test_password_is_never_stored_in_the_clear():
    secret = "correct horse battery"
    stored = auth.hash_password(secret)
    assert secret not in stored
    assert stored.startswith("scrypt$")
    assert auth.verify_password(secret, stored)
    assert not auth.verify_password("wrong", stored)


def test_same_password_hashes_differently_each_time():
    """Per-user salt — identical passwords must not collide in the table."""
    assert auth.hash_password("same-password") != auth.hash_password("same-password")


def test_malformed_hash_is_rejected_not_crashed():
    for junk in ["", "nonsense", "bcrypt$x$y", "scrypt$!!!$!!!"]:
        assert auth.verify_password("x", junk) is False


# ---------------------------------------------------------------------- tokens


def test_forged_and_expired_tokens_are_rejected():
    good = auth.issue_token("usr_1", "a@example.com")
    assert auth.read_token(good)["sub"] == "usr_1"

    header, payload, sig = good.split(".")
    assert auth.read_token(f"{header}.{payload}.{'A' * len(sig)}") is None  # bad signature
    assert auth.read_token("not-a-token") is None
    assert auth.read_token("") is None

    # A token whose claims were swapped keeps the old signature -> rejected.
    other = auth.issue_token("usr_2", "b@example.com")
    assert auth.read_token(f"{header}.{other.split('.')[1]}.{sig}") is None


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_TTL_SECONDS", -1)
    assert auth.read_token(auth.issue_token("usr_1", "a@example.com")) is None


# ------------------------------------------------------------------ signup/login


def test_signup_then_login(client):
    _signup(client, "new@example.com")
    r = client.post(
        "/api/auth/login",
        json={"email": "new@example.com", "password": "correct horse battery"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "new@example.com"


def test_duplicate_email_is_rejected(client):
    _signup(client, "dupe@example.com")
    r = client.post(
        "/api/auth/signup",
        json={"email": "dupe@example.com", "password": "another password"},
    )
    assert r.status_code == 409


def test_wrong_password_and_unknown_email_are_indistinguishable(client):
    """Different messages would tell an attacker which emails exist."""
    _signup(client, "real@example.com")
    wrong = client.post(
        "/api/auth/login", json={"email": "real@example.com", "password": "not it at all"}
    )
    missing = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "not it at all"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]


def test_short_password_is_rejected(client):
    r = client.post("/api/auth/signup", json={"email": "x@example.com", "password": "short"})
    assert r.status_code == 422


# ------------------------------------------------------------------- isolation


def test_one_tenant_cannot_read_anothers_run(client):
    alice = _signup(client, "alice@example.com")
    bob = _signup(client, "bob@example.com")

    rid = client.post(
        "/api/runs",
        json={"mode": "demo", "persona_name": "appointment_booking"},
        headers=_auth(alice),
    ).json()["id"]
    _finish(client, rid, _auth(alice))

    # Bob knows the id and asks for it directly.
    assert client.get(f"/api/runs/{rid}", headers=_auth(bob)).status_code == 404
    assert client.get(f"/api/runs/{rid}/delta", headers=_auth(bob)).status_code == 404
    assert client.get("/api/runs", headers=_auth(bob)).json() == []
    # ...and the anonymous demo tenant cannot see it either.
    assert client.get(f"/api/runs/{rid}").status_code == 404


def test_scenarios_and_agents_are_per_tenant(client):
    alice, bob = _signup(client, "a2@example.com"), _signup(client, "b2@example.com")
    spec = {"name": "mine", "goal": "g", "opening": "hi", "turns": [],
            "success_criteria": ["ok"]}

    assert client.post("/api/scenarios", json=spec, headers=_auth(alice)).status_code == 201
    client.post("/api/agents", json={"label": "prod", "agent_id": "agent_x"},
                headers=_auth(alice))

    assert [s["name"] for s in client.get("/api/personas", headers=_auth(bob)).json()
            if s["source"] == "saved"] == []
    assert client.get("/api/agents", headers=_auth(bob)).json() == []
    # Same name is fine for a different tenant — uniqueness is per-owner.
    assert client.post("/api/scenarios", json=spec, headers=_auth(bob)).status_code == 201


def test_baselines_do_not_leak_across_tenants(client):
    """Alice's fast run must not become the baseline Bob is judged against."""
    alice, bob = _signup(client, "a3@example.com"), _signup(client, "b3@example.com")
    body = {"mode": "demo", "persona_name": "appointment_booking"}

    rid = client.post("/api/runs", json=body, headers=_auth(alice)).json()["id"]
    _finish(client, rid, _auth(alice))

    slow = {**body, "latency_bias_ms": 250}
    rid2 = client.post("/api/runs", json=slow, headers=_auth(bob)).json()["id"]
    run = _finish(client, rid2, _auth(bob))
    # Bob's first run has nothing of his own to compare against.
    assert run["status"] == "passed"
    assert run["failures"] == []


def test_saved_scenario_shadows_a_bundled_one(client):
    token = _signup(client, "shadow@example.com")
    client.post(
        "/api/scenarios",
        json={"name": "appointment_booking", "goal": "custom", "opening": "hello there",
              "turns": [], "success_criteria": ["anything"]},
        headers=_auth(token),
    )
    rid = client.post(
        "/api/runs", json={"mode": "demo", "persona_name": "appointment_booking"},
        headers=_auth(token),
    ).json()["id"]
    run = _finish(client, rid, _auth(token))
    assert run["report"]["goal"] == "custom"
    assert len(run["report"]["turns"]) == 1


# ------------------------------------------------------------ demo + guards


def test_public_demo_needs_no_account(client):
    """The landing page must work for a first-time visitor."""
    r = client.post("/api/runs", json={"mode": "demo", "persona_name": "impatient_refund"})
    assert r.status_code == 202
    run = _finish(client, r.json()["id"], {})
    assert run["metrics"]["goal_completed"] is True
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_account_only_routes_reject_the_demo_tenant(client):
    assert client.get("/api/agents").status_code == 401
    assert client.post("/api/agents", json={"label": "x", "agent_id": "y"}).status_code == 401
    assert client.post(
        "/api/scenarios",
        json={"name": "n", "goal": "", "opening": "o", "turns": [], "success_criteria": []},
    ).status_code == 401


def test_invalid_token_is_401_not_a_silent_demo_fallback(client):
    """Falling back to the demo tenant here would hide an expired session."""
    r = client.get("/api/runs", headers={"Authorization": "Bearer garbage.token.here"})
    assert r.status_code == 401


def test_trend_returns_history_oldest_first(client):
    token = _signup(client, "trend@example.com")
    for _ in range(3):
        rid = client.post(
            "/api/runs", json={"mode": "demo", "persona_name": "appointment_booking"},
            headers=_auth(token),
        ).json()["id"]
        _finish(client, rid, _auth(token))

    points = client.get("/api/trends/appointment_booking", headers=_auth(token)).json()
    assert len(points) == 3
    assert [p["created_at"] for p in points] == sorted(p["created_at"] for p in points)
    assert all(p["ttfa_ms_p95"] > 0 for p in points)
