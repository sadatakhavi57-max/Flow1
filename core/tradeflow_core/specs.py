"""Item specification input validation and snapshot - contract section 12.

The Service is the only author of the snapshot. Its shape is exactly what trigger
trg_request_items_validate_specifications (002) accepts: keys field_id, field_code, field_name, data_type, value;
data_type UPPERCASE; field_id a UUID of a field of the same organization whose code/data_type match.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from .digits import normalize_decimal_separator, normalize_digits
from .errors import AppError, ErrorCode

DATA_TYPES = ("TEXT", "NUMBER", "DECIMAL", "BOOLEAN", "DATE", "SELECT", "MULTI_SELECT")
_NUMBER_RE = re.compile(r"^-?[0-9]{1,18}$")
_DECIMAL_RE = re.compile(r"^-?[0-9]{1,12}(\.[0-9]{1,6})?$")   # NUMERIC(18,6): 12 integer digits at most
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_INPUT_KEYS = {"field_id", "value"}


@dataclass(frozen=True)
class FieldDef:
    id: str
    code: str
    name: str
    data_type: str
    is_active: bool = True
    is_required: bool = False
    options: tuple[str, ...] | None = None

    def __post_init__(self):
        if self.data_type not in DATA_TYPES:
            raise ValueError(f"unknown data_type {self.data_type!r}")
        if self.data_type in ("SELECT", "MULTI_SELECT"):
            if not self.options or not all(isinstance(o, str) for o in self.options):
                raise ValueError("SELECT/MULTI_SELECT fields need options: a non-empty list of strings (D3)")


class _Invalid(Exception):
    pass


def canonical_value(field: FieldDef, value: Any) -> Any:
    """Return the canonical JSON value or raise _Invalid. Table of section 12."""
    t = field.data_type
    if t == "TEXT":
        if not isinstance(value, str):
            raise _Invalid
        s = value.strip()
        if not 1 <= len(s) <= 1000:
            raise _Invalid
        return s
    if t == "NUMBER":
        if not isinstance(value, str):
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
        s = normalize_decimal_separator(normalize_digits(value.strip()))
        if not _DECIMAL_RE.match(s):
            raise _Invalid
        neg = s.startswith("-")
        ip, _, fp = s.lstrip("-").partition(".")
        ip = ip.lstrip("0") or "0"
        fp = fp.rstrip("0")
        out = ip + ("." + fp if fp else "")
        return "-" + out if neg and out != "0" else out
    if t == "BOOLEAN":
        if not isinstance(value, bool):
            raise _Invalid
        return value
    if t == "DATE":
        if not isinstance(value, str):
            raise _Invalid
        s = normalize_digits(value.strip())
        if not _DATE_RE.match(s):
            raise _Invalid
        try:
            return date(int(s[:4]), int(s[5:7]), int(s[8:])).isoformat()
        except ValueError:
            raise _Invalid
    if t == "SELECT":
        if not isinstance(value, str) or value not in field.options:
            raise _Invalid
        return value
    if t == "MULTI_SELECT":
        if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
            raise _Invalid
        if len(set(value)) != len(value) or any(v not in field.options for v in value):
            raise _Invalid
        return [o for o in field.options if o in set(value)]      # order of the field's options
    raise _Invalid  # pragma: no cover


def _is_uuid(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    try:
        return str(uuid.UUID(s)) == s.lower()
    except ValueError:
        return False


def build_snapshot(inputs: Any, fields: dict[str, FieldDef], applicable_ids: Iterable[str]) -> list[dict]:
    """inputs: the client's `specifications` array. fields: ALL fields of the organization by id.
    applicable_ids: ids of fields applicable to the item's product (section 7 / D3).
    Raises VALIDATION_ERROR for malformed structure, SPECIFICATION_INVALID (details [{field_id, reason}]) otherwise."""
    if not isinstance(inputs, list):
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "specifications", "reason": "MUST_BE_ARRAY"}])
    applicable = {str(i).lower() for i in applicable_ids}
    fields = {k.lower(): v for k, v in fields.items()}

    for i, el in enumerate(inputs):                                  # structure first: exactly {field_id, value}
        if not isinstance(el, dict) or set(el) != _INPUT_KEYS:
            raise AppError(ErrorCode.VALIDATION_ERROR,
                           details=[{"field": f"specifications[{i}]", "reason": "EXPECTED_KEYS_field_id_AND_value"}])
        if not _is_uuid(el["field_id"]):
            raise AppError(ErrorCode.VALIDATION_ERROR,
                           details=[{"field": f"specifications[{i}].field_id", "reason": "NOT_A_UUID"}])

    problems, snapshot, seen = [], [], set()
    for el in inputs:
        fid = el["field_id"].lower()
        f = fields.get(fid)
        if f is None:
            problems.append({"field_id": fid, "reason": "UNKNOWN_FIELD"}); continue
        if fid not in applicable:
            problems.append({"field_id": fid, "reason": "NOT_APPLICABLE"}); continue
        if not f.is_active:
            problems.append({"field_id": fid, "reason": "INACTIVE_FIELD"}); continue
        if fid in seen:
            problems.append({"field_id": fid, "reason": "DUPLICATE_FIELD"}); continue
        seen.add(fid)
        try:
            v = canonical_value(f, el["value"])
        except _Invalid:
            problems.append({"field_id": fid, "reason": "INVALID_VALUE"}); continue
        snapshot.append({"field_id": fid, "field_code": f.code, "field_name": f.name,
                         "data_type": f.data_type, "value": v})
    if problems:
        raise AppError(ErrorCode.SPECIFICATION_INVALID, details=problems)
    return snapshot


def missing_required(required_field_ids: Iterable[str], snapshot: list[dict]) -> list[str]:
    """Submit check (D6): applicable, active, is_required fields absent from the snapshot. Sorted for determinism."""
    have = {e["field_id"].lower() for e in snapshot}
    return sorted(str(r).lower() for r in required_field_ids if str(r).lower() not in have)
