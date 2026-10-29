"""Optimistic concurrency - contract sections 14.5 and 17 (D7). Microsecond precision, exact string."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .errors import AppError, ErrorCode

_TS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})Z$")


def format_ts(dt: datetime) -> str:
    """The API timestamp: ISO 8601 UTC with six fractional digits, e.g. 2026-10-08T09:20:11.123456Z."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def parse_ts(s) -> datetime:
    if not isinstance(s, str) or not _TS.match(s):
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "updated_at", "reason": "INVALID_FORMAT"}])
    y, mo, d, h, mi, se, us = map(int, _TS.match(s).groups())
    try:
        return datetime(y, mo, d, h, mi, se, us, tzinfo=timezone.utc)
    except ValueError:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "updated_at", "reason": "INVALID_FORMAT"}])


def check_not_stale(client_updated_at, stored: datetime, current_resource=None) -> None:
    """Called AFTER the row lock is taken (14.2). Missing -> VALIDATION_ERROR, mismatch -> STALE_UPDATE + current resource."""
    if client_updated_at is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "updated_at", "reason": "REQUIRED"}])
    if parse_ts(client_updated_at) != stored.astimezone(timezone.utc):
        raise AppError(ErrorCode.STALE_UPDATE, details={"current": current_resource})
