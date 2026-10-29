"""Optimistic concurrency - contract sections 14.5 and 17."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .errors import DomainError

_TS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z$")


def parse_updated_at(value) -> datetime:
    if not isinstance(value, str):
        raise DomainError("VALIDATION_ERROR", "updated_at is required.", [{"field": "updated_at", "reason": "REQUIRED"}])
    m = _TS.match(value.strip())
    if not m:
        raise DomainError("VALIDATION_ERROR", "updated_at must be the exact value last returned by the API.",
                          [{"field": "updated_at", "reason": "FORMAT"}])
    y, mo, d, h, mi, s, frac = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), int((frac or "0").ljust(6, "0")), tzinfo=timezone.utc)
    except ValueError:
        raise DomainError("VALIDATION_ERROR", "updated_at is not a real timestamp.", [{"field": "updated_at", "reason": "FORMAT"}])


def check_updated_at(client_value, stored: datetime, current_resource=None) -> None:
    """Compare at microsecond precision AFTER the row lock (14.2). Mismatch -> 409 STALE_UPDATE + details.current."""
    got = parse_updated_at(client_value)
    if got != stored.astimezone(timezone.utc):
        raise DomainError("STALE_UPDATE", "The resource was changed by someone else.", {"current": current_resource})
