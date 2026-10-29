"""Customer input rules - contract section 6. The database normalizes identifiers; this module mirrors that for
validation and search only, and the mirror is tested against the real PostgreSQL function normalize_identifier."""
from __future__ import annotations

import re

from . import inputs
from .digits import normalize_digits
from .errors import AppError, ErrorCode
from .money import parse_money

# 002 uses [[:space:]] + ZWNJ, LRM, RLM, NBSP. [[:space:]] is locale dependent in PostgreSQL: under the C locale
# (the test databases) it is ASCII-only; a UTF-8 locale may also match e.g. U+2003. The mirror follows the C-locale
# behaviour verified against the real function - see CONTRACT_GAPS.md.
_WS = re.compile("[ \t\n\r\f\v\u200c\u200e\u200f\u00a0]")
TYPES = ("INDIVIDUAL", "COMPANY")
FIELDS = ("customer_type", "name", "national_id", "economic_code", "registration_number", "mobile", "phone", "email",
          "address", "postal_code", "credit_limit", "is_active")
_LIMITS = {"name": 255, "national_id": 50, "economic_code": 50, "registration_number": 50, "mobile": 30, "phone": 50,
           "email": 255, "address": inputs.TEXT_LIMIT, "postal_code": 20}


def normalize_identifier(p: str | None) -> str | None:
    """Python mirror of 002 normalize_identifier(): digits to ASCII, remove whitespace/ZWNJ/LRM/RLM/NBSP, '' -> NULL."""
    if p is None:
        return None
    s = _WS.sub("", normalize_digits(p))
    return s or None


def _fields(body: dict, names, *, creating: bool) -> dict:
    out: dict = {}
    for f in names:
        if f not in body:
            continue
        v = body[f]
        if f == "customer_type":
            if v not in TYPES:
                raise inputs.verr(f, "MUST_BE_INDIVIDUAL_OR_COMPANY")
            out[f] = v
        elif f == "name":
            out[f] = inputs.text(v, f, 255, required=True)
        elif f in ("national_id", "economic_code"):
            if v is not None and not isinstance(v, str):
                raise inputs.verr(f, "MUST_BE_STRING")
            n = normalize_identifier(v)
            if n is not None and len(n) > 50:
                raise inputs.verr(f, "MAX_LENGTH_50")
            out[f] = n
        elif f == "credit_limit":
            out[f] = parse_money(v, f)
        elif f == "is_active":
            out[f] = inputs.parse_bool(v, f)
        else:
            out[f] = inputs.text(v, f, _LIMITS[f])
    return out


def parse_create(body) -> dict:
    inputs.strict_object(body, FIELDS, required=("customer_type", "name"))
    out = _fields(body, FIELDS, creating=True)
    out.setdefault("credit_limit", 0)
    out.setdefault("is_active", True)
    for f in FIELDS:
        out.setdefault(f, None)
    return out


def parse_patch(body) -> tuple[dict, str]:
    """Any subset of the fields plus the mandatory `updated_at` (D7). Returns (changes, updated_at_string)."""
    inputs.strict_object(body, FIELDS + ("updated_at",), required=("updated_at",))
    changes = _fields(body, FIELDS, creating=False)
    return changes, body["updated_at"]


def search_terms(q: str | None) -> dict | None:
    """Case-insensitive contains on name/national_id/economic_code/mobile with digits normalized."""
    s = inputs.text(q, "search", 100)
    if s is None:
        return None
    return {"text": s.lower(), "identifier": normalize_identifier(s)}
