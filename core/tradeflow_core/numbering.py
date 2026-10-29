"""Request number - contract section 8, D1: '<jalali year of the creation instant in Asia/Tehran>-<n:06d>'.

Two separate things are kept apart on purpose:
  * the series (Jalali year) is derived ONCE, from the creation instant, when the request is created, and is then just
    text inside request_number - it is never recomputed from created_at and never used for display;
  * the sequence number n is the database counter next_request_number(organization_id, series) (ADR-057) - uniqueness
    never depends on dates; MAX()+1 is forbidden.
Display of dates (Jalali or otherwise) is a client concern; the API only speaks Gregorian.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .jalali import jalali_year

TEHRAN = ZoneInfo("Asia/Tehran")
SUPPORTED_YEARS = range(1400, 1500)       # algorithms A and B agree on 1365..1528; 1470 and 1503 have equinoxes within
#                                           ~12 / 5 minutes of noon (jalali_astro.minutes_from_noon) - outside this slice's horizon
_NUMBER_RE = re.compile(r"^(1[0-9]{3})-([0-9]{6,})$")


def series_for(created_at: datetime) -> str:
    """Jalali year (as text) of an aware instant, evaluated on the Asia/Tehran calendar date."""
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware (UTC instants only; never local naive time)")
    jy = jalali_year(created_at.astimezone(TEHRAN).date())
    if jy not in SUPPORTED_YEARS:
        raise ValueError(f"Jalali year {jy} is outside the verified range {SUPPORTED_YEARS.start}..{SUPPORTED_YEARS.stop - 1}")
    return str(jy)


def format_request_number(series: str, n: int) -> str:
    if not re.fullmatch(r"1[0-9]{3}", series):
        raise ValueError("series must be a 4-digit Jalali year")
    if n < 1:
        raise ValueError("sequence numbers start at 1")
    return f"{series}-{n:06d}"            # above 999999 the number simply gets longer


def parse_request_number(s: str) -> tuple[str, int]:
    m = _NUMBER_RE.match(s)
    if not m:
        raise ValueError(f"not a request number: {s!r}")
    return m.group(1), int(m.group(2))


def tehran_today(now: datetime):
    """Today's Gregorian date in Tehran - the reference for the delivery-date rule (section 8)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(TEHRAN).date()
