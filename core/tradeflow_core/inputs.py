"""Shared input helpers - contract section 2 (strings, unknown keys, UUIDs, pagination)."""
from __future__ import annotations

import re
import uuid
from typing import Any, Iterable

from .errors import AppError, ErrorCode

# keys the server owns: a client sending them gets a precise reason (never silently ignored)
SERVER_OWNED = frozenset({"id", "organization_id", "created_at", "created_by", "updated_by", "status", "request_number",
                          "subtotal", "discount_total", "tax_total", "grand_total", "line_total", "request_date",
                          "purchase_request_id"})
TEXT_LIMIT = 5000          # implementation limit for unbounded TEXT columns (the contract sets none) - see CONTRACT_GAPS.md


def verr(field: str, reason: str) -> AppError:
    return AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": field, "reason": reason}])


def strict_object(body: Any, allowed: Iterable[str], *, required: Iterable[str] = ()) -> dict:
    """The body must be a JSON object with only allowed keys (extra = forbid). All offending keys are reported together."""
    if not isinstance(body, dict):
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "$", "reason": "MUST_BE_OBJECT"}])
    allowed = set(allowed)
    problems = []
    for k in sorted(body):
        if k not in allowed:
            problems.append({"field": str(k), "reason": "NOT_ALLOWED" if k in SERVER_OWNED else "UNKNOWN_FIELD"})
    for k in sorted(set(required) - set(body)):
        problems.append({"field": k, "reason": "REQUIRED"})
    if problems:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=problems)
    return body


def text(value, field: str, max_len: int, *, required: bool = False) -> str | None:
    """Trim; '' -> None for optional fields. Non-strings are rejected."""
    if value is None:
        if required:
            raise verr(field, "REQUIRED")
        return None
    if not isinstance(value, str):
        raise verr(field, "MUST_BE_STRING")
    s = value.strip()
    if not s:
        if required:
            raise verr(field, "REQUIRED")
        return None
    if len(s) > max_len:
        raise verr(field, f"MAX_LENGTH_{max_len}")
    return s


def parse_uuid(value, field: str) -> str:
    if isinstance(value, str):
        try:
            u = uuid.UUID(value.strip())
            if str(u) == value.strip().lower():
                return str(u)
        except ValueError:
            pass
    raise verr(field, "NOT_A_UUID")


def parse_bool(value, field: str) -> bool:
    if not isinstance(value, bool):
        raise verr(field, "MUST_BE_BOOLEAN")
    return value


_INT = re.compile(r"^[0-9]{1,9}$")


def parse_pagination(page=None, page_size=None) -> tuple[int, int]:
    """page >= 1 (default 1); page_size 1..200 (default 50). Query-string values arrive as str."""
    def num(v, name, default, lo, hi):
        if v is None:
            return default
        s = str(v).strip()
        if not _INT.match(s) or isinstance(v, bool):
            raise verr(name, "MUST_BE_INTEGER")
        n = int(s)
        if not lo <= n <= hi:
            raise verr(name, f"RANGE_{lo}_{hi}")
        return n
    return num(page, "page", 1, 1, 10**9), num(page_size, "page_size", 50, 1, 200)


def list_envelope(items: list, page: int, page_size: int, total: int) -> dict:
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def data_envelope(data, request_id: str) -> dict:
    return {"data": data, "request_id": request_id}
