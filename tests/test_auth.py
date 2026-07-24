"""Clerk-backed identity and tenant isolation.

Clerk owns sign-up/sign-in, so there are no credential endpoints to test here.
What still matters — and matters more — is that a verified Clerk user id scopes
every read and write: a SaaS that leaks one customer's runs to another is worse
than one with no accounts at all.

`clerk_auth.verify_token` is the seam. Tests stub it so isolation can be proven
without minting real RS256 tokens against a live Clerk instance.
"""

import base64
import time

import pytest
from fastapi.testclient import TestClient

from server import clerk_auth, store
from server.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "auth.db")
    store.init()

    # Stand in for Clerk: "tok_<user>" verifies to Clerk user id "user_<user>".
    # Anything else fails, exactly as a forged or expired token would.
    def fake_verify(token: str):
        return f"user_{token[4:]}" if token.startswith("tok_") else None

    monkeypatch.setattr(clerk_auth, "verify_token", fake_verify)
    with TestClient(app) as c:
        yield c


def _as(user: str) -> dict:
    """Headers for a signed-in Clerk user."""
    return {"Authorization": f"Bearer tok_{user}"}


def _finish(client, run_id, headers, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}", headers=headers).json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


# ------------------------------------------------------------- token verifying


def test_jwks_url_is_derived_from_the_publishable_key(monkeypatch):
    # Clerk publishable keys end in a base64 blob of the frontend API host.
    host = "clerk.example.dev$"
    pk = "pk_test_" + base64.b64encode(host.encode()).decode()
    monkeypatch.setattr(clerk_auth, "CLERK_JWKS_URL", None)
    monkeypatch.setattr(clerk_auth, "CLERK_PUBLISHABLE_KEY", pk)
    assert clerk_auth._derive_jwks_url() == "https://clerk.example.dev/.well-known/jwks.json"


def test_explicit_jwks_url_wins(monkeypatch):
    monkeypatch.setattr(clerk_auth, "CLERK_JWKS_URL", "https://pinned/jwks.json")
    monkeypatch.setattr(clerk_auth, "CLERK_PUBLISHABLE_KEY", "pk_test_garbage")
    assert clerk_auth._derive_jwks_url() == "https://pinned/jwks.json"


def test_unconfigured_clerk_verifies_nothing(monkeypatch):
    """Without Clerk config the backend must reject tokens, never trust them."""
    monkeypatch.setattr(clerk_auth, "CLERK_JWKS_URL", None)
    monkeypatch.setattr(clerk_auth, "CLERK_PUBLISHABLE_KEY", None)
    monkeypatch.setattr(clerk_auth, "_jwks_client", None)
    assert clerk_auth.is_configured() is False
    assert clerk_auth.verify_token("anything.at.all") is None


def test_malformed_publishable_key_does_not_crash(monkeypatch):
    monkeypatch.setattr(clerk_auth, "CLERK_JWKS_URL", None)
    monkeypatch.setattr(clerk_auth, "CLERK_PUBLISHABLE_KEY", "pk_test_!!!not-base64!!!")
    assert clerk_auth._derive_jwks_url() is None


# ------------------------------------------------------------------- isolation


def test_one_tenant_cannot_read_anothers_run(client):
    rid = client.post(
        "/api/runs",
        json={"mode": "demo", "persona_name": "appointment_booking"},
        headers=_as("alice"),
    ).json()["id"]
    _finish(client, rid, _as("alice"))

    # Bob knows the id and asks for it directly.
    assert client.get(f"/api/runs/{rid}", headers=_as("bob")).status_code == 404
    assert client.get(f"/api/runs/{rid}/delta", headers=_as("bob")).status_code == 404
    assert client.get("/api/runs", headers=_as("bob")).json() == []
    # ...and the anonymous demo tenant cannot see it either.
    assert client.get(f"/api/runs/{rid}").status_code == 404


def test_scenarios_and_agents_are_per_tenant(client):
    spec = {"name": "mine", "goal": "g", "opening": "hi", "turns": [],
            "success_criteria": ["ok"]}

    assert client.post("/api/scenarios", json=spec, headers=_as("alice")).status_code == 201
    client.post("/api/agents", json={"label": "prod", "agent_id": "agent_x"},
                headers=_as("alice"))

    assert [s["name"] for s in client.get("/api/personas", headers=_as("bob")).json()
            if s["source"] == "saved"] == []
    assert client.get("/api/agents", headers=_as("bob")).json() == []
    # Same name is fine for a different tenant — uniqueness is per-owner.
    assert client.post("/api/scenarios", json=spec, headers=_as("bob")).status_code == 201


def test_baselines_do_not_leak_across_tenants(client):
    """Alice's fast run must not become the baseline Bob is judged against."""
    body = {"mode": "demo", "persona_name": "appointment_booking"}

    rid = client.post("/api/runs", json=body, headers=_as("alice")).json()["id"]
    _finish(client, rid, _as("alice"))

    slow = {**body, "latency_bias_ms": 250}
    rid2 = client.post("/api/runs", json=slow, headers=_as("bob")).json()["id"]
    run = _finish(client, rid2, _as("bob"))
    # Bob's first run has nothing of his own to compare against.
    assert run["status"] == "passed"
    assert run["failures"] == []


def test_saved_scenario_shadows_a_bundled_one(client):
    client.post(
        "/api/scenarios",
        json={"name": "appointment_booking", "goal": "custom", "opening": "hello there",
              "turns": [], "success_criteria": ["anything"]},
        headers=_as("shadow"),
    )
    rid = client.post(
        "/api/runs", json={"mode": "demo", "persona_name": "appointment_booking"},
        headers=_as("shadow"),
    ).json()["id"]
    run = _finish(client, rid, _as("shadow"))
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


def test_signed_in_me_reports_the_clerk_user(client):
    body = client.get("/api/auth/me", headers=_as("alice")).json()
    assert body["authenticated"] is True
    assert body["owner"] == "user_alice"


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
    for _ in range(3):
        rid = client.post(
            "/api/runs", json={"mode": "demo", "persona_name": "appointment_booking"},
            headers=_as("trend"),
        ).json()["id"]
        _finish(client, rid, _as("trend"))

    points = client.get("/api/trends/appointment_booking", headers=_as("trend")).json()
    assert len(points) == 3
    assert [p["created_at"] for p in points] == sorted(p["created_at"] for p in points)
    assert all(p["ttfa_ms_p95"] > 0 for p in points)
