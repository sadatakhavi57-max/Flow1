"""Authentication use-cases (contract section 3). Policy lives in tradeflow_core; this file only wires it to the database."""
from __future__ import annotations

from datetime import datetime, timezone

from tradeflow_core import audit, auth_inputs
from tradeflow_core.errors import AppError, ErrorCode
from tradeflow_core.passwords import needs_rehash, hash_password, verify_or_dummy
from tradeflow_core.ratelimit import LoginRateLimiter, normalize_key
from tradeflow_core.tokens import (RefreshService, issue_access_token, verify_access_token)

from . import auth_repo


class AuthService:
    def __init__(self, db, settings, limiter: LoginRateLimiter | None = None, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.cfg, self.clock = db, settings.core, clock
        self.limiter = limiter or LoginRateLimiter()
        self.refresh_svc = RefreshService(auth_repo.PgRefreshStore(db), clock, self.cfg.refresh_grace_seconds, self.cfg.refresh_ttl_days)

    # -------------------------------------------------------------- helpers
    def _svc(self, conn) -> RefreshService:
        return RefreshService(auth_repo.BoundStore(conn), self.clock, self.cfg.refresh_grace_seconds, self.cfg.refresh_ttl_days)

    def _tokens(self, p: auth_repo.Principal, refresh_raw: str) -> dict:
        access, _ = issue_access_token(self.cfg.jwt_secret, p.user_id, p.org_id, self.clock(), self.cfg.access_ttl_seconds)
        return {"access_token": access, "refresh_token": refresh_raw, "token_type": "bearer",
                "expires_in": self.cfg.access_ttl_seconds, "user": p.user_json()}

    def _audit(self, conn, action, p, ip):
        auth_repo.insert_audit(conn, audit.build_entry(action, "USER", organization_id=p.org_id, user_id=p.user_id,
                                                       entity_id=p.user_id, ip_address=ip))

    # -------------------------------------------------------------- use-cases
    def login(self, body, ip: str) -> dict:
        org, username, password = auth_inputs.parse_login(body)
        key = normalize_key(org, username, ip or "")
        self.limiter.check(key)
        with self.db.tx() as conn:
            p = auth_repo.find_for_login(conn, org, username)
        ok = verify_or_dummy(password, p.password_hash if p else None)
        if not (ok and p and p.active):
            self.limiter.record_failure(key)                     # D4: failed logins are counted, not audited
            raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS)
        with self.db.tx() as conn:                                  # token + last_login + audit: one atomic unit
            issued = self._svc(conn).login_issue(p.user_id, p.org_id)
            auth_repo.touch_login(conn, p.user_id, hash_password(password) if needs_rehash(p.password_hash) else None)
            self._audit(conn, "LOGIN", p, ip)
        return self._tokens(p, issued.raw)

    def refresh(self, body) -> dict:
        raw = auth_inputs.parse_refresh_body(body)
        issued = self.refresh_svc.refresh(raw)
        with self.db.tx() as conn:
            p = auth_repo.load_principal(conn, issued.row.user_id, issued.row.org_id)
        if p is None or not p.active:
            raise AppError(ErrorCode.AUTH_REFRESH_INVALID, details={"reason": "INVALID"})
        return self._tokens(p, issued.raw)

    def authenticate(self, authorization: str | None) -> auth_repo.Principal:
        """Bearer token -> a freshly loaded, active principal. Every failure is the same AUTH_TOKEN_INVALID."""
        bad = AppError(ErrorCode.AUTH_TOKEN_INVALID)
        if not authorization:
            raise bad
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise bad
        claims = verify_access_token(self.cfg.jwt_secret, token.strip(), self.clock())
        with self.db.tx() as conn:
            p = auth_repo.load_principal(conn, claims["sub"], claims["org"])
        if p is None or not p.active:
            raise bad
        return p

    def logout(self, principal: auth_repo.Principal, body, ip: str) -> None:
        raw = auth_inputs.parse_refresh_body(body)
        with self.db.tx() as conn:                                  # revoke + audit: one atomic unit
            self._svc(conn).logout(raw, principal.user_id, principal.org_id)
            self._audit(conn, "LOGOUT", principal, ip)
