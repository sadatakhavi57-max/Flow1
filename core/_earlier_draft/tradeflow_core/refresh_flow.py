"""Refresh rotation orchestration - the logic that sits between the HTTP handler and the repository.

`tx` is a repository bound to ONE open database transaction (the caller opens/commits/rolls back). Required methods:
    fetch_refresh_for_update(token_hash) -> None | dict(id, user_id, revoked_at, expires_at)   # SELECT ... FOR UPDATE
    user_is_active(user_id) -> bool                                  # user, role and organization all active
    revoke_refresh(row_id, now); revoke_all_refresh(user_id, now)
    insert_refresh(user_id, token_hash, expires_at)
Returns (raw_new_refresh_token, user_id) on success or raises DomainError AUTH_REFRESH_INVALID(details.reason).
NOTE: the revoke-all side effect of an INVALID outcome must be COMMITTED although the request fails:
`rotate_refresh` therefore returns an Outcome instead of raising when a write has to survive; the handler commits and
then raises `outcome.error`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import tokens
from .errors import DomainError


@dataclass
class Outcome:
    new_refresh_token: str | None = None
    user_id: str | None = None
    error: DomainError | None = None
    commit: bool = True


def rotate_refresh(tx, raw_token: str, now: datetime, grace_seconds: int = tokens.REFRESH_GRACE_SECONDS) -> Outcome:
    row = tx.fetch_refresh_for_update(tokens.hash_refresh_token(raw_token))
    d = tokens.decide_refresh(row, now, grace_seconds)
    if d.action == tokens.ROTATE:
        if not tx.user_is_active(row["user_id"]):
            tx.revoke_refresh(row["id"], now)                      # a deactivated user cannot keep refreshing
            return Outcome(error=DomainError("AUTH_REFRESH_INVALID", "Refresh token is not valid.", {"reason": tokens.INVALID}))
        tx.revoke_refresh(row["id"], now)
        raw, h = tokens.new_refresh_token()
        tx.insert_refresh(row["user_id"], h, tokens.refresh_expiry(now))
        return Outcome(new_refresh_token=raw, user_id=row["user_id"])
    if d.revoke_all_for_user:
        tx.revoke_all_refresh(row["user_id"], now)
    return Outcome(error=d.error(), commit=d.revoke_all_for_user)   # ALREADY_ROTATED: nothing written
