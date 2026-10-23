"""Identity use cases; persistence and cryptographic primitives arrive through ports."""
from __future__ import annotations

from typing import Any, Callable


class IdentityService:
    def __init__(self, repository: Any, hash_secret: Callable[[str], str],
                 verify_secret: Callable[[str, str], bool], issue_token: Callable[..., str],
                 verify_token: Callable[..., dict[str, Any] | None], secret: str, token_ttl_seconds: int,
                 allow_signup: bool) -> None:
        self.repository = repository
        self._hash_secret, self._verify_secret = hash_secret, verify_secret
        self._issue_token, self._verify_token = issue_token, verify_token
        self.secret, self.token_ttl_seconds, self.allow_signup = secret, token_ttl_seconds, allow_signup

    def register(self, email: str, display_name: str, password: str, organization_name: str) -> dict[str, Any]:
        if not self.repository:
            raise RuntimeError("Identity storage is unavailable.")
        password_hash = self._hash_secret(password)
        if self.allow_signup:
            actor = self.repository.create_account(email, display_name, password_hash, organization_name)
        else:
            actor = self.repository.create_initial_account(email, display_name, password_hash, organization_name)
        self.repository.audit(actor, "auth.account.created", actor["user_id"])
        return self._session(actor)

    def hash_password(self, password: str) -> str:
        return self._hash_secret(password)

    def login(self, email: str, password: str) -> dict[str, Any]:
        if not self.repository:
            raise RuntimeError("Identity storage is unavailable.")
        user = self.repository.find_user(email)
        if not user or not self._verify_secret(password, user["password_hash"]):
            raise ValueError("邮箱或密码不正确。")
        actor = {key: user[key] for key in ("user_id", "organization_id", "role", "email", "display_name", "token_version")}
        self.repository.audit(actor, "auth.login", actor["user_id"])
        return self._session(actor)

    def authenticate(self, token: str) -> dict[str, Any] | None:
        if not token or not self.repository:
            return None
        actor = self._verify_token(token, self.secret)
        if not actor:
            return None
        role = self.repository.member_role(actor["user_id"], actor["organization_id"])
        version = self.repository.session_version(actor["user_id"])
        if not role or version is None or actor.get("token_version", 0) != version:
            return None
        actor["role"] = role
        return actor

    def _session(self, actor: dict[str, Any]) -> dict[str, Any]:
        return {"access_token": self._issue_token(actor, self.secret, self.token_ttl_seconds),
                "token_type": "bearer", "user": actor}
