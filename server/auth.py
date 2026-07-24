"""Accounts and tenant identity.

Self-contained on purpose: no external auth provider to sign up for, so the
whole product deploys from this repo alone. Passwords are hashed with scrypt
(stdlib, memory-hard); sessions are signed JWTs.

Two rules the rest of the server depends on:
- a password is never stored, logged, or returned — only its scrypt hash
- every query that touches tenant data takes the owner id from the *token*,
  never from a request body, so a caller cannot read another tenant's runs
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

# Signing key for session tokens. Generated per-process when unset so local dev
# needs no setup; production must pin it or every restart logs everyone out.
SECRET = os.environ.get("SOUNDCHECK_SECRET") or secrets.token_hex(32)
TOKEN_TTL_SECONDS = 7 * 24 * 3600

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


# --------------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    """`scrypt$<salt>$<hash>` — salt is per-user, never reused."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    # Constant-time: a timing difference here leaks how much of the hash matched.
    return hmac.compare_digest(candidate, expected)


# ------------------------------------------------------------------------ tokens


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(user_id: str, email: str) -> str:
    """Minimal HS256 JWT — no dependency, and the shape is standard."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {"sub": user_id, "email": email, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    signature = hmac.new(SECRET.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(signature)}"


def read_token(token: str) -> Optional[dict]:
    """Return the claims, or None if the token is forged, malformed or expired."""
    try:
        header, payload, signature = token.split(".")
    except ValueError:
        return None
    expected = hmac.new(
        SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(_unb64url(signature), expected):
        return None
    try:
        claims = json.loads(_unb64url(payload))
    except (ValueError, TypeError):
        return None
    if claims.get("exp", 0) < time.time():
        return None
    return claims
