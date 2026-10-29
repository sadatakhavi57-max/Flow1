"""Request state machine and submit/cancel rules - contract sections 8 and 14 (ADR-061 C5, ADR-062, D6, D8, D9)."""
from __future__ import annotations

from decimal import Decimal

from .errors import DomainError

DRAFT, SUBMITTED, CANCELLED = "DRAFT", "SUBMITTED", "CANCELLED"
STATUSES = (DRAFT, SUBMITTED, CANCELLED)
ALLOWED = {(DRAFT, SUBMITTED), (DRAFT, CANCELLED), (SUBMITTED, CANCELLED)}      # exactly the database rule


def ensure_transition(old: str, new: str) -> None:
    if (old, new) not in ALLOWED:
        raise DomainError("STATE_CONFLICT", f"Cannot change status {old} -> {new}.", {"from": old, "to": new})


def ensure_content_editable(status: str) -> None:
    """D9: header (notes included), items and prices may be changed only while DRAFT - stricter than the database."""
    if status != DRAFT:
        raise DomainError("STATE_CONFLICT", "Only a draft request can be edited.", {"status": status})


def cancel_reason(value) -> str:
    """Required, 1..500 characters AFTER trimming (D8)."""
    if not isinstance(value, str):
        raise DomainError("VALIDATION_ERROR", "reason is required.", [{"field": "reason", "reason": "REQUIRED"}])
    s = value.strip()
    if not 1 <= len(s) <= 500:
        raise DomainError("VALIDATION_ERROR", "reason must be 1..500 characters.", [{"field": "reason", "reason": "LENGTH"}])
    return s


def check_submit(status: str, customer_active: bool, items: list) -> None:
    """Section 8 'Submit', in the documented order. `items`: dicts with keys
    id, unit_price (Decimal), product_active, unit_active, snapshot (list), required_field_ids (iterable of ids of
    applicable required fields of the item's product)."""
    if status != DRAFT:
        raise DomainError("STATE_CONFLICT", "Only a draft request can be submitted.", {"status": status})
    if not customer_active or any(not (i["product_active"] and i["unit_active"]) for i in items):
        raise DomainError("INACTIVE_REFERENCE", "The customer, a product or a unit is inactive.")
    if not items:
        raise DomainError("SUBMIT_PRECONDITION_FAILED", "A request needs at least one item.", {"reason": "NO_ITEMS"})
    for i in items:
        if Decimal(i["unit_price"]) <= 0:
            raise DomainError("SUBMIT_PRECONDITION_FAILED", "Every item needs a unit price.",
                              {"reason": "ITEM_PRICE_MISSING", "item_id": i["id"]})
    for i in items:
        have = {e["field_id"] for e in i["snapshot"]}
        missing = sorted(f for f in i["required_field_ids"] if f not in have)
        if missing:
            raise DomainError("SUBMIT_PRECONDITION_FAILED", "A required specification is missing.",
                              {"reason": "REQUIRED_SPECIFICATION_MISSING", "item_id": i["id"], "field_id": missing[0]})
