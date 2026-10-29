"""Access JWT and refresh-token policy - contract section 3 (D10).

* Access token: HS256, 3600 s, claims sub, org, iat, exp, jti. The role is NOT in the token.
* Refresh token: opaque 256-bit random; only SHA-256 (hex) is stored; rotated on every use.
* Duplicate-tolerant policy with a grace window: see decide_refresh().  The pure decision function is what the Service
  runs after `SELECT ... FROM refresh_tokens WHERE token_hash = :h FOR UPDATE`; RefreshService below shows the full
  transaction against an abstract store, and InMemoryStore serialises transactions the way the row lock does.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Protocol

import jwt

from .errors import AppError, ErrorCode

ACCESS_TTL_SECONDS = 3600
REFRESH_TTL_DAYS = 30
REFRESH_GRACE_SECONDS = 10
MIN_SECRET_BYTES = 32


# ------------------------------------------------------------------ access token
def _check_secret(secret) -> bytes:
    b = secret.encode() if isinstance(secret, str) else secret
    if not isinstance(b, (bytes, bytearray)) or len(b) < MIN_SECRET_BYTES:
        raise ValueError(f"JWT secret must be at least {MIN_SECRET_BYTES} bytes")
    return bytes(b)


def issue_access_token(secret, user_id: str, org_id: str, now: datetime, ttl: int = ACCESS_TTL_SECONDS) -> tuple[str, dict]:
    key = _check_secret(secret)
    iat = int(now.timestamp())
    claims = {"sub": str(user_id), "org": str(org_id), "iat": iat, "exp": iat + ttl, "jti": str(uuid.uuid4())}
    return jwt.encode(claims, key, algorithm="HS256"), claims


def verify_access_token(secret, token, now: datetime) -> dict:
    """Any problem -> AUTH_TOKEN_INVALID (never says why). Algorithm is pinned: 'none' and RS/ES tokens are rejected."""
    key = _check_secret(secret)
    bad = AppError(ErrorCode.AUTH_TOKEN_INVALID)
    if not isinstance(token, str) or not token:
        raise bad
    try:
        if jwt.get_unverified_header(token).get("alg") != "HS256":
            raise bad
        c = jwt.decode(token, key, algorithms=["HS256"],
                       options={"require": ["exp", "iat", "sub", "org", "jti"], "verify_exp": False, "verify_iat": False})
    except AppError:
        raise
    except Exception:
        raise bad
    try:
        uuid.UUID(c["sub"]); uuid.UUID(c["org"])
        exp, iat = int(c["exp"]), int(c["iat"])
    except Exception:
        raise bad
    if int(now.timestamp()) >= exp or exp - iat > ACCESS_TTL_SECONDS:
        raise bad
    return c


# ------------------------------------------------------------------ refresh token
def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)                       # 256 bits
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class RefreshRow:
    id: str
    user_id: str
    org_id: str
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None


class Decision(str, Enum):
    ROTATE = "ROTATE"
    ALREADY_ROTATED = "ALREADY_ROTATED"
    INVALID = "INVALID"


def decide_refresh(row: RefreshRow | None, now: datetime, grace_seconds: int = REFRESH_GRACE_SECONDS) -> tuple[Decision, bool]:
    """Returns (decision, revoke_all_active_tokens_of_user). Contract section 3, in this order:
    1. unknown token                                 -> INVALID (no user is known, so nothing can be revoked)
    2. revoked <= grace seconds ago                  -> ALREADY_ROTATED, nothing else revoked (benign duplicate)
    3. revoked longer ago                            -> INVALID + revoke all (real reuse)
    4. not revoked but expired                       -> INVALID + revoke all (as written in the contract)
    5. not revoked, not expired                      -> ROTATE
    """
    if row is None:
        return Decision.INVALID, False
    if row.revoked_at is not None:
        if (now - row.revoked_at).total_seconds() <= grace_seconds:
            return Decision.ALREADY_ROTATED, False
        return Decision.INVALID, True
    if now >= row.expires_at:
        return Decision.INVALID, True
    return Decision.ROTATE, False


class Tx(Protocol):
    def lock_by_hash(self, token_hash: str) -> RefreshRow | None: ...
    def revoke(self, row_id: str, now: datetime) -> None: ...
    def revoke_all_active(self, user_id: str, now: datetime) -> int: ...
    def insert(self, row: RefreshRow) -> None: ...


class InMemoryStore:
    """Test double. `transaction()` holds ONE lock for its whole duration: transactions are fully serialised, which is the
    guarantee `SELECT ... FOR UPDATE` gives for the same token row. It does NOT prove the PostgreSQL locking itself."""

    def __init__(self):
        self.rows: dict[str, RefreshRow] = {}
        self._lock = threading.Lock()

    @contextmanager
    def transaction(self):
        with self._lock:
            yield self

    def lock_by_hash(self, h): return next((r for r in self.rows.values() if r.token_hash == h), None)
    def revoke(self, row_id, now): self.rows[row_id] = replace(self.rows[row_id], revoked_at=now)
    def insert(self, row): self.rows[row.id] = row

    def revoke_all_active(self, user_id, now):
        n = 0
        for i, r in list(self.rows.items()):
            if r.user_id == user_id and r.revoked_at is None:
                self.rows[i] = replace(r, revoked_at=now); n += 1
        return n


@dataclass
class Issued:
    raw: str
    row: RefreshRow


class RefreshService:
    def __init__(self, store, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 grace_seconds: int = REFRESH_GRACE_SECONDS, ttl_days: int = REFRESH_TTL_DAYS):
        self.store, self.now, self.grace, self.ttl = store, now, grace_seconds, ttl_days

    def _issue(self, tx: Tx, user_id: str, org_id: str, now: datetime) -> Issued:
        raw, h = new_refresh_token()
        row = RefreshRow(str(uuid.uuid4()), user_id, org_id, h, now + timedelta(days=self.ttl))
        tx.insert(row)
        return Issued(raw, row)

    def login_issue(self, user_id: str, org_id: str) -> Issued:
        with self.store.transaction() as tx:
            return self._issue(tx, user_id, org_id, self.now())

    def refresh(self, raw: str) -> Issued:
        """One transaction: lock the row, decide, rotate or revoke. The revoke-all of the theft case is COMMITTED
        before the error is raised (raising inside the transaction would roll the revocation back)."""
        now = self.now()
        outcome: Issued | AppError
        with self.store.transaction() as tx:
            row = tx.lock_by_hash(hash_refresh_token(raw)) if isinstance(raw, str) and raw else None
            decision, revoke_all = decide_refresh(row, now, self.grace)
            if decision is Decision.ROTATE:
                tx.revoke(row.id, now)
                outcome = self._issue(tx, row.user_id, row.org_id, now)
            else:
                if revoke_all:
                    tx.revoke_all_active(row.user_id, now)
                outcome = AppError(ErrorCode.AUTH_REFRESH_INVALID,
                                   details={"reason": "ALREADY_ROTATED" if decision is Decision.ALREADY_ROTATED else "INVALID"})
        if isinstance(outcome, AppError):
            raise outcome
        return outcome

    def logout(self, raw: str, caller_user_id: str, caller_org_id: str) -> None:
        """Revokes only the caller's own token (same user and organization). Anything else: AUTH_REFRESH_INVALID, nothing
        revoked, no hint whether the token exists. An already-revoked own token is a successful no-op (idempotent)."""
        now = self.now()
        with self.store.transaction() as tx:
            row = tx.lock_by_hash(hash_refresh_token(raw)) if isinstance(raw, str) and raw else None
            if row is None or row.user_id != caller_user_id or row.org_id != caller_org_id:
                ok = False
            else:
                ok = True
                if row.revoked_at is None:
                    tx.revoke(row.id, now)
        if not ok:
            raise AppError(ErrorCode.AUTH_REFRESH_INVALID, details={"reason": "INVALID"})
