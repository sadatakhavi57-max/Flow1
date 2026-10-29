"""Purchase-request state machine, freeze rules and submit/cancel preconditions (sections 8, 14)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from .errors import AppError, field_error
from .specifications import missing_required

DRAFT, SUBMITTED, CANCELLED = "DRAFT", "SUBMITTED", "CANCELLED"
STATUSES = (DRAFT, SUBMITTED, CANCELLED)

# Exactly the database rules of ADR-061 (C5); anything else raises SQLSTATE 55000 in the trigger.
ALLOWED_TRANSITIONS = frozenset({(DRAFT, SUBMITTED), (DRAFT, CANCELLED), (SUBMITTED, CANCELLED)})


def check_transition(current: str, target: str) -> None:
    if (current, target) not in ALLOWED_TRANSITIONS:
        raise AppError("STATE_CONFLICT", {"from": current, "to": target})


def ensure_draft(status: str) -> None:
    """Header PATCH, item create/patch/delete and pricing are DRAFT-only [D9]: in SUBMITTED and CANCELLED
    nothing - not even notes - may be edited through the API (stricter than the database)."""
    if status != DRAFT:
        raise AppError("STATE_CONFLICT", {"status": status})


def normalize_cancel_reason(reason) -> str:
    if not isinstance(reason, str):
        raise field_error("VALIDATION_ERROR", "reason", "REQUIRED")
    r = reason.strip()
    if not 1 <= len(r) <= 500:
        raise field_error("VALIDATION_ERROR", "reason", "LENGTH_1_TO_500_AFTER_TRIM")
    return r


@dataclass(frozen=True)
class ItemForSubmit:
    id: str
    unit_price: Decimal
    product_active: bool
    unit_active: bool
    specifications: Sequence[Mapping]            # stored snapshot
    required_field_ids: Sequence[str]            # applicable fields with is_required = true (current definitions)


def check_submit(status: str, customer_active: bool, items: Iterable[ItemForSubmit]) -> None:
    """Section 8 'Submit', steps 1-5, in that order; the first failure wins."""
    items = list(items)
    if status != DRAFT:
        raise AppError("STATE_CONFLICT", {"status": status})                       # repeat submit -> 409
    if not customer_active or any(not (i.product_active and i.unit_active) for i in items):
        raise AppError("INACTIVE_REFERENCE")
    if not items:
        raise AppError("SUBMIT_PRECONDITION_FAILED", {"reason": "NO_ITEMS"})
    for i in items:
        if i.unit_price <= 0:
            raise AppError("SUBMIT_PRECONDITION_FAILED", {"reason": "ITEM_PRICE_MISSING", "item_id": i.id})
    for i in items:
        missing = missing_required(i.specifications, i.required_field_ids)
        if missing:
            raise AppError("SUBMIT_PRECONDITION_FAILED",
                           {"reason": "REQUIRED_SPECIFICATION_MISSING", "item_id": i.id, "field_id": missing[0]})
