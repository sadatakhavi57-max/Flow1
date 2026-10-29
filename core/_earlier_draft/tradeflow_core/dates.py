"""Dates - contract sections 2 and 8. Gregorian only, ASCII digits; Tehran business day."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .digits import to_ascii_digits
from .errors import DomainError

TEHRAN = ZoneInfo("Asia/Tehran")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def parse_gregorian_date(value, field: str = "date") -> date:
    if not isinstance(value, str):
        raise DomainError("VALIDATION_ERROR", f"{field} must be a YYYY-MM-DD string.", [{"field": field, "reason": "NOT_A_STRING"}])
    t = to_ascii_digits(value.strip())
    if not _DATE.match(t):
        raise DomainError("VALIDATION_ERROR", f"{field} must be YYYY-MM-DD.", [{"field": field, "reason": "FORMAT"}])
    try:
        return date(int(t[:4]), int(t[5:7]), int(t[8:10]))
    except ValueError:
        raise DomainError("VALIDATION_ERROR", f"{field} is not a real date.", [{"field": field, "reason": "NOT_A_REAL_DATE"}])


def tehran_date(instant: datetime) -> date:
    if instant.tzinfo is None:
        raise ValueError("naive datetime: pass an aware instant (stored values are TIMESTAMPTZ)")
    return instant.astimezone(TEHRAN).date()


def validate_delivery_date(value, now: datetime, request_date: datetime | None = None) -> date | None:
    """Rule (1) of section 8 (Service): optional; real Gregorian date; not before today in Asia/Tehran.
    Rule (2) (not before the request's own request_date) is enforced by the database CHECK; when
    `request_date` is given it is also checked here so the client gets a clean 422 instead of a 23514 mapping."""
    if value is None:
        return None
    d = parse_gregorian_date(value, "requested_delivery_date")
    today = tehran_date(now)
    if d < today:
        raise DomainError("VALIDATION_ERROR", "Delivery date is before today (Asia/Tehran).",
                          [{"field": "requested_delivery_date", "reason": "BEFORE_TODAY"}])
    if request_date is not None and d < tehran_date(request_date):
        raise DomainError("VALIDATION_ERROR", "Delivery date is before the request date.",
                          [{"field": "requested_delivery_date", "reason": "BEFORE_REQUEST_DATE"}])
    return d


def iso_utc(instant: datetime) -> str:
    """Timestamps leave the API as ISO 8601 UTC with microseconds: 2026-10-08T09:20:11.123456Z."""
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
