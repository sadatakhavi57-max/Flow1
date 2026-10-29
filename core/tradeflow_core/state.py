"""Purchase-request state machine, content freeze and submit rules - contract section 8 (ADR-061 C5, D6, D8, D9, D13)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from .errors import AppError, ErrorCode
from .specs import missing_required


class Status(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"


ALLOWED_TRANSITIONS = frozenset({(Status.DRAFT, Status.SUBMITTED), (Status.DRAFT, Status.CANCELLED),
                                 (Status.SUBMITTED, Status.CANCELLED)})


def assert_transition(current: str, new: str) -> None:
    """Exactly the database rules of 002 (errcode 55000 there); the API reports STATE_CONFLICT."""
    try:
        pair = (Status(current), Status(new))
    except ValueError:
        raise AppError(ErrorCode.STATE_CONFLICT)
    if pair not in ALLOWED_TRANSITIONS:
        raise AppError(ErrorCode.STATE_CONFLICT, details={"from": pair[0].value, "to": pair[1].value})


def assert_editable(status: str) -> None:
    """D9: header, notes, items and prices change only in DRAFT - stricter than the database (which lets notes change)."""
    if status != Status.DRAFT.value:
        raise AppError(ErrorCode.STATE_CONFLICT, details={"status": status})


def validate_cancel_reason(reason) -> str:
    """D8: required, 1-500 characters after trimming."""
    if not isinstance(reason, str):
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "reason", "reason": "REQUIRED"}])
    r = reason.strip()
    if not 1 <= len(r) <= 500:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "reason", "reason": "LENGTH_1_TO_500"}])
    return r


def assert_product_unchanged(old_product_id: str, patch: dict) -> None:
    """D13: an item's product cannot change (delete and re-add instead)."""
    if "product_id" in patch and str(patch["product_id"]).lower() != str(old_product_id).lower():
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "product_id", "reason": "IMMUTABLE"}])


@dataclass(frozen=True)
class SubmitItem:
    id: str
    product_active: bool
    unit_active: bool
    unit_price: Decimal
    snapshot: list = field(default_factory=list)
    required_field_ids: tuple = ()          # applicable, ACTIVE fields with is_required (section 8 step 5)


def check_submit(status: str, customer_active: bool, items: list[SubmitItem]) -> None:
    """Section 8 'Submit', in the contract's order; first failure wins and is deterministic."""
    if status != Status.DRAFT.value:
        raise AppError(ErrorCode.STATE_CONFLICT, details={"status": status})
    inactive = []
    if not customer_active:
        inactive.append({"resource": "customer"})
    for it in items:
        if not it.product_active:
            inactive.append({"resource": "product", "item_id": it.id})
        if not it.unit_active:
            inactive.append({"resource": "unit", "item_id": it.id})
    if inactive:
        raise AppError(ErrorCode.INACTIVE_REFERENCE, details=inactive)
    if not items:
        raise AppError(ErrorCode.SUBMIT_PRECONDITION_FAILED, details={"reason": "NO_ITEMS"})
    for it in items:
        if it.unit_price <= 0:
            raise AppError(ErrorCode.SUBMIT_PRECONDITION_FAILED, details={"reason": "ITEM_PRICE_MISSING", "item_id": it.id})
    for it in items:
        miss = missing_required(it.required_field_ids, it.snapshot)
        if miss:
            raise AppError(ErrorCode.SUBMIT_PRECONDITION_FAILED,
                           details={"reason": "REQUIRED_SPECIFICATION_MISSING", "item_id": it.id, "field_id": miss[0]})
