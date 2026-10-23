"""Minimal signed session tokens and password hashing for optional enterprise auth."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any

import jwt


PBKDF2_ROUNDS = 600_000
TOKEN_ISSUER = "product-research-agent"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, _b64decode(expected))
    except (ValueError, TypeError):
        return False


def issue_token(actor: dict[str, Any], secret: str, ttl_seconds: int = 8 * 3600) -> str:
    now = int(time.time())
    payload = {"iss": TOKEN_ISSUER, "sub": actor["user_id"], "org": actor["organization_id"],
               "role": actor["role"], "ver": int(actor.get("token_version", 0)),
               "iat": now, "exp": now + max(60, ttl_seconds)}
    return str(jwt.encode(payload, secret, algorithm="HS256"))


def verify_token(token: str, secret: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], issuer=TOKEN_ISSUER,
                             options={"require": ["iss", "sub", "org", "role", "iat", "exp"]})
        if not all(payload.get(key) for key in ("sub", "org", "role")):
            return None
        return {"user_id": str(payload["sub"]), "organization_id": str(payload["org"]),
                "role": str(payload["role"]), "token_version": int(payload.get("ver", 0))}
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        return None
