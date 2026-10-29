"""Optimistic concurrency on `updated_at` (contract sections 14.5 and 17)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .errors import AppError, field_error

_TS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})Z$")


def format_timestamp(dt: datetime) -> str:
    """ISO 8601 UTC with microseconds: 2026-10-08T09:20:11.123456Z"""
    if dt.tzinfo is None:
        raise ValueError("aware datetime required")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_timestamp(s, field: str = "updated_at") -> datetime:
    """The exact string last returned by the API; any other shape is a 422 (never guessed)."""
    if not isinstance(s, str):
        raise field_error("VALIDATION_ERROR", field, "REQUIRED")
    m = _TS.match(s)
    if not m:
        raise field_error("VALIDATION_ERROR", field, "BAD_TIMESTAMP_FORMAT")
    try:
        y, mo, d, h, mi, sec, us = map(int, m.groups())
        return datetime(y, mo, d, h, mi, sec, us, tzinfo=timezone.utc)
    except ValueError:
        raise field_error("VALIDATION_ERROR", field, "BAD_TIMESTAMP_FORMAT") from None


def check_fresh(client_value, stored: datetime, current_resource: dict | None = None) -> None:
    """Compare at microsecond precision AFTER the row lock was taken; mismatch -> 409 STALE_UPDATE with the
    current resource in details.current."""
    if parse_timestamp(client_value) != stored.astimezone(timezone.utc):
        raise AppError("STALE_UPDATE", {"current": current_resource})
