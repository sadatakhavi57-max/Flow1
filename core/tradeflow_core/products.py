"""Product input rules - contract section 7, plus lookup/list filter parsing."""
from __future__ import annotations

from . import inputs

FIELDS = ("code", "name", "description", "category_id", "default_unit_id", "is_active")
UNIT_TYPES = ("QUANTITY", "WEIGHT", "LENGTH", "AREA", "VOLUME", "TIME")


def _fields(body: dict) -> dict:
    out: dict = {}
    for f in FIELDS:
        if f not in body:
            continue
        v = body[f]
        if f == "code":
            out[f] = inputs.text(v, f, 100, required=True)
        elif f == "name":
            out[f] = inputs.text(v, f, 255, required=True)
        elif f == "description":
            out[f] = inputs.text(v, f, inputs.TEXT_LIMIT)
        elif f in ("category_id", "default_unit_id"):
            out[f] = inputs.parse_uuid(v, f)
        else:
            out[f] = inputs.parse_bool(v, f)
    return out


def parse_create(body) -> dict:
    inputs.strict_object(body, FIELDS, required=("code", "name", "category_id", "default_unit_id"))
    out = _fields(body)
    out.setdefault("description", None)
    out.setdefault("is_active", True)
    return out


def parse_patch(body) -> tuple[dict, str]:
    inputs.strict_object(body, FIELDS + ("updated_at",), required=("updated_at",))
    return _fields(body), body["updated_at"]


def parse_bool_filter(value, field: str = "is_active") -> bool | None:
    """Query-string boolean: absent -> None; 'true'/'false' only."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s == "true":
        return True
    if s == "false":
        return False
    raise inputs.verr(field, "MUST_BE_TRUE_OR_FALSE")


def parse_unit_type_filter(value) -> str | None:
    if value is None:
        return None
    if value not in UNIT_TYPES:
        raise inputs.verr("unit_type", "UNKNOWN_UNIT_TYPE")
    return value
