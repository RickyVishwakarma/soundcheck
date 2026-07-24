"""Verify Clerk session tokens.

Clerk owns sign-up/sign-in on the frontend and issues RS256 JWTs. The backend
only *verifies* them: it fetches Clerk's public keys (JWKS) and, on a valid
token, treats the Clerk user id (`sub`) as the tenant `owner`. There is no
password or user table here anymore — Clerk is the identity provider.

`verify_token` is the single seam the API depends on, so tests can monkeypatch
it and exercise tenant isolation without minting real RS256 tokens.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

# JWKS URL comes from env in prod. Otherwise it's derived from the Clerk
# publishable key, whose suffix base64-decodes to the instance's frontend API
# host (e.g. "clerk.your-app.dev$" -> https://clerk.your-app.dev/.well-known/jwks.json).
CLERK_JWKS_URL = os.environ.get("CLERK_JWKS_URL")
CLERK_PUBLISHABLE_KEY = os.environ.get(
    "CLERK_PUBLISHABLE_KEY"
) or os.environ.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")

_jwks_client = None


def _derive_jwks_url() -> Optional[str]:
    if CLERK_JWKS_URL:
        return CLERK_JWKS_URL
    if not CLERK_PUBLISHABLE_KEY:
        return None
    try:
        suffix = CLERK_PUBLISHABLE_KEY.split("_", 2)[2]
        host = base64.b64decode(suffix + "==").decode().rstrip("$")
        return f"https://{host}/.well-known/jwks.json"
    except (IndexError, ValueError, UnicodeDecodeError):
        return None


def _client():
    """Lazily build a cached JWKS client; None when unconfigured or PyJWT absent."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    url = _derive_jwks_url()
    if not url:
        return None
    try:
        from jwt import PyJWKClient
    except ImportError:  # pragma: no cover - optional dep
        return None
    _jwks_client = PyJWKClient(url)
    return _jwks_client


def verify_token(token: str) -> Optional[str]:
    """Return the Clerk user id for a valid token, else None.

    Signature, expiry and not-before are all checked; audience is not (Clerk
    session tokens don't carry an `aud` the backend needs to pin).
    """
    client = _client()
    if client is None:
        return None
    try:
        import jwt

        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except Exception:
        return None
    return claims.get("sub")


def is_configured() -> bool:
    return _derive_jwks_url() is not None
