"""Purchase-request, item, pricing and cancel inputs - contract sections 8, 9, 10, 11."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import inputs
from .digits import normalize_digits
from .errors import AppError, ErrorCode
from .money import (parse_bundle_count, parse_estimated_weight, parse_money, parse_quantity)
from .specs import _DATE_RE
from .state import validate_cancel_reason

ITEM_FIELDS = ("product_id", "unit_id", "quantity", "bundle_count", "estimated_weight", "unit_price",
               "discount_amount", "tax_amount", "notes", "specifications")
PRICE_FIELDS = ("unit_price", "discount_amount", "tax_amount")
REQUEST_FIELDS = ("customer_id", "requested_delivery_date", "notes")


def parse_delivery_date(value, today: date, field: str = "requested_delivery_date") -> date | None:
    """Optional. Gregorian YYYY-MM-DD (digits normalized), a real date, not before today in Asia/Tehran (same day ok).
    The database separately enforces 'not before request_date' (002 C1) - see contract section 8."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise inputs.verr(field, "MUST_BE_STRING")
    s = normalize_digits(value.strip())
    if not s:
        return None
    if not _DATE_RE.match(s):
        raise inputs.verr(field, "INVALID_DATE")
    try:
        d = date(int(s[:4]), int(s[5:7]), int(s[8:]))
    except ValueError:
        raise inputs.verr(field, "INVALID_DATE")
    if d < today:
        raise inputs.verr(field, "BEFORE_TODAY")
    return d


def _item_fields(body: dict, creating: bool) -> dict:
    out: dict = {}
    for f in ITEM_FIELDS:
        if f not in body:
            continue
        v = body[f]
        if f in ("product_id", "unit_id"):
            out[f] = inputs.parse_uuid(v, f)
        elif f == "quantity":
            out[f] = parse_quantity(v)
        elif f == "bundle_count":
            out[f] = parse_bundle_count(v)
        elif f == "estimated_weight":
            out[f] = parse_estimated_weight(v)
        elif f in PRICE_FIELDS:
            out[f] = parse_money(v, f)
        elif f == "notes":
            out[f] = inputs.text(v, f, inputs.TEXT_LIMIT)
        elif f == "specifications":
            if not isinstance(v, list):
                raise inputs.verr(f, "MUST_BE_ARRAY")
            out[f] = v                                    # element validation needs the database fields: specs.build_snapshot
    return out


def parse_item_create(body) -> dict:
    """unit_id stays absent when not given: the Service fills it from the product's default_unit_id (D2)."""
    inputs.strict_object(body, ITEM_FIELDS, required=("product_id", "quantity"))
    out = _item_fields(body, True)
    out.setdefault("bundle_count", Decimal(0))
    out.setdefault("estimated_weight", None)
    out.setdefault("notes", None)
    out.setdefault("specifications", [])
    for f in PRICE_FIELDS:
        out.setdefault(f, Decimal(0))
    return out


def parse_item_patch(body) -> tuple[dict, str]:
    inputs.strict_object(body, ITEM_FIELDS + ("updated_at",), required=("updated_at",))
    return _item_fields(body, False), body["updated_at"]


def parse_request_create(body, today: date) -> dict:
    inputs.strict_object(body, REQUEST_FIELDS + ("items",), required=("customer_id",))
    items = body.get("items", [])
    if items is None:
        items = []
    if not isinstance(items, list):
        raise inputs.verr("items", "MUST_BE_ARRAY")
    return {"customer_id": inputs.parse_uuid(body["customer_id"], "customer_id"),
            "requested_delivery_date": parse_delivery_date(body.get("requested_delivery_date"), today),
            "notes": inputs.text(body.get("notes"), "notes", inputs.TEXT_LIMIT),
            "items": [parse_item_create(i) for i in items]}


def parse_request_patch(body, today: date) -> tuple[dict, str]:
    inputs.strict_object(body, REQUEST_FIELDS + ("updated_at",), required=("updated_at",))
    ch: dict = {}
    if "customer_id" in body:
        ch["customer_id"] = inputs.parse_uuid(body["customer_id"], "customer_id")
    if "requested_delivery_date" in body:
        ch["requested_delivery_date"] = parse_delivery_date(body["requested_delivery_date"], today)
    if "notes" in body:
        ch["notes"] = inputs.text(body["notes"], "notes", inputs.TEXT_LIMIT)
    return ch, body["updated_at"]


def parse_pricing(body) -> tuple[list[dict], str]:
    """POST /purchase-requests/{id}/pricing: all-or-nothing batch. Each line must price at least one field; item_id unique."""
    inputs.strict_object(body, ("updated_at", "lines"), required=("updated_at", "lines"))
    lines = body["lines"]
    if not isinstance(lines, list) or not lines:
        raise inputs.verr("lines", "MUST_BE_NON_EMPTY_ARRAY")
    out, seen = [], set()
    for i, ln in enumerate(lines):
        inputs.strict_object(ln, ("item_id",) + PRICE_FIELDS, required=("item_id",))
        item_id = inputs.parse_uuid(ln["item_id"], f"lines[{i}].item_id")
        if item_id in seen:
            raise inputs.verr(f"lines[{i}].item_id", "DUPLICATE_ITEM")
        seen.add(item_id)
        prices = {f: parse_money(ln[f], f"lines[{i}].{f}") for f in PRICE_FIELDS if f in ln}
        if not prices:
            raise inputs.verr(f"lines[{i}]", "NO_PRICE_FIELD")
        out.append({"item_id": item_id, **prices})
    return out, body["updated_at"]


def parse_cancel(body) -> str:
    inputs.strict_object(body, ("reason",), required=("reason",))
    return validate_cancel_reason(body["reason"])


def parse_date_param(value, field: str) -> date | None:
    """Query-string calendar date (created_from / created_to): Gregorian YYYY-MM-DD, digits normalized, any past or future day."""
    if value is None:
        return None
    s = normalize_digits(str(value).strip())
    if not _DATE_RE.match(s):
        raise inputs.verr(field, "INVALID_DATE")
    try:
        return date(int(s[:4]), int(s[5:7]), int(s[8:]))
    except ValueError:
        raise inputs.verr(field, "INVALID_DATE")
