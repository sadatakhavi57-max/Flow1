"""Specification values and the immutable per-item snapshot (contract section 12, ADR-061 C6).

The client sends [{"field_id", "value"}] and nothing else.  The Service is the only author of the stored
snapshot [{"field_id","field_code","field_name","data_type","value"}], built from the field row at save time.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from .digits import normalize_decimal_text, normalize_digits
from .errors import AppError, field_error

DATA_TYPES = ("TEXT", "NUMBER", "DECIMAL", "BOOLEAN", "DATE", "SELECT", "MULTI_SELECT")

_NUMBER_RE = re.compile(r"^-?[0-9]{1,18}$")
_DECIMAL_RE = re.compile(r"^-?[0-9]{1,12}(\.[0-9]{1,6})?$")        # NUMERIC(18,6): 12 integer digits at most
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_TEXT_MAX = 1000


@dataclass(frozen=True)
class FieldDef:
    id: str                      # UUID string
    code: str
    name: str
    data_type: str
    options: tuple[str, ...] | None = None
    is_active: bool = True
    is_required: bool = False


class _Invalid(Exception):
    """Internal: value fails its type rule."""


def canonicalize_value(field: FieldDef, value: Any) -> Any:
    """Return the canonical JSON form of `value` for `field.data_type` or raise _Invalid."""
    t = field.data_type
    if t == "TEXT":
        if not isinstance(value, str):
            raise _Invalid
        s = value.strip()
        if not 1 <= len(s) <= _TEXT_MAX:
            raise _Invalid
        return s
    if t == "NUMBER":
        if not isinstance(value, str):                    # JSON numbers and booleans are rejected
            raise _Invalid
        s = normalize_digits(value.strip())
        if not _NUMBER_RE.match(s):
            raise _Invalid
        neg = s.startswith("-")
        digits = s.lstrip("-").lstrip("0") or "0"
        return "-" + digits if neg and digits != "0" else digits
    if t == "DECIMAL":
        if not isinstance(value, str):
            raise _Invalid
        s = normalize_decimal_text(value.strip())
        if not _DECIMAL_RE.match(s):
            raise _Invalid
        neg = s.startswith("-")
        body = s.lstrip("-")
        ip, _, fp = body.partition(".")
        ip = ip.lstrip("0") or "0"
        fp = fp.rstrip("0")
        out = ip + ("." + fp if fp else "")
        return "-" + out if neg and out != "0" else out
    if t == "BOOLEAN":
        if value is True or value is False:
            return value
        raise _Invalid
    if t == "DATE":
        if not isinstance(value, str):
            raise _Invalid
        s = normalize_digits(value.strip())
        if not _DATE_RE.match(s):
            raise _Invalid
        try:
            date(int(s[0:4]), int(s[5:7]), int(s[8:10]))      # a real Gregorian date
        except ValueError:
            raise _Invalid
        return s
    if t == "SELECT":
        if not isinstance(value, str) or field.options is None or value not in field.options:
            raise _Invalid
        return value
    if t == "MULTI_SELECT":
        if (not isinstance(value, list) or not value or field.options is None
                or any(not isinstance(v, str) for v in value)
                or len(set(value)) != len(value)
                or any(v not in field.options for v in value)):
            raise _Invalid
        return [o for o in field.options if o in value]       # order of the field's options
    raise _Invalid


def _is_uuid(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    try:
        return str(uuid.UUID(s)) == s.lower()
    except ValueError:
        return False


def build_snapshot(items: Any, fields: Mapping[str, FieldDef], applicable_field_ids: Iterable[str]) -> list[dict]:
    """Validate client input and build the snapshot.

    fields               every specification field of the caller's organization, keyed by lower-case UUID
                         (so an id of another organization is simply absent: UNKNOWN_FIELD, never revealed).
    applicable_field_ids fields of ACTIVE templates whose category equals the product's category [D3]
                         (field.is_active is checked separately, which makes INACTIVE_FIELD reachable).

    Per element the first failing rule wins, in the order of the contract:
    UNKNOWN_FIELD, NOT_APPLICABLE, INACTIVE_FIELD, DUPLICATE_FIELD, INVALID_VALUE.  All failing elements are
    reported: 422 SPECIFICATION_INVALID details = [{field_id, reason}].
    """
    if items is None:
        return []
    if not isinstance(items, list):
        raise field_error("VALIDATION_ERROR", "specifications", "MUST_BE_ARRAY")
    for i, el in enumerate(items):                                # shape: exactly field_id + value
        if not isinstance(el, dict):
            raise field_error("VALIDATION_ERROR", f"specifications[{i}]", "MUST_BE_OBJECT")
        extra = set(el) - {"field_id", "value"}
        if extra:
            raise field_error("VALIDATION_ERROR", f"specifications[{i}]", "UNEXPECTED_KEYS:" + ",".join(sorted(extra)))
        if set(el) != {"field_id", "value"}:
            raise field_error("VALIDATION_ERROR", f"specifications[{i}]", "MISSING_KEYS")
        if not _is_uuid(el["field_id"]):
            raise field_error("VALIDATION_ERROR", f"specifications[{i}].field_id", "NOT_A_UUID")

    applicable = {a.lower() for a in applicable_field_ids}
    seen: set[str] = set()
    problems: list[dict] = []
    snapshot: list[dict] = []
    for el in items:
        fid = el["field_id"].lower()
        f = fields.get(fid)
        if f is None:
            problems.append({"field_id": el["field_id"], "reason": "UNKNOWN_FIELD"})
            continue
        if fid not in applicable:
            problems.append({"field_id": el["field_id"], "reason": "NOT_APPLICABLE"})
            continue
        if not f.is_active:
            problems.append({"field_id": el["field_id"], "reason": "INACTIVE_FIELD"})
            continue
        if fid in seen:
            problems.append({"field_id": el["field_id"], "reason": "DUPLICATE_FIELD"})
            continue
        seen.add(fid)
        try:
            v = canonicalize_value(f, el["value"])
        except _Invalid:
            problems.append({"field_id": el["field_id"], "reason": "INVALID_VALUE"})
            continue
        snapshot.append({"field_id": f.id, "field_code": f.code, "field_name": f.name,
                         "data_type": f.data_type, "value": v})
    if problems:
        raise AppError("SPECIFICATION_INVALID", problems)
    return snapshot


def missing_required(snapshot: Sequence[Mapping], required_field_ids: Iterable[str]) -> list[str]:
    """Submit check (section 8, step 5): applicable required fields absent from the snapshot."""
    have = {str(e["field_id"]).lower() for e in snapshot}
    return [r for r in required_field_ids if r.lower() not in have]
