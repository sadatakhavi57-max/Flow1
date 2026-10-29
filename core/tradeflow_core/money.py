"""Money, quantity and line-total rules - contract section 10 (ADR-058).

Whole Rial, Decimal only (never float), ROUND_HALF_UP.  The database re-checks the result with
    line_total = ROUND(quantity * unit_price - discount_amount + tax_amount, 0)      (001, chk_request_items_line_total_consistency)
and PostgreSQL rounds half away from zero; for the non-negative values allowed here that equals ROUND_HALF_UP.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Iterable

from .digits import normalize_digits
from .errors import AppError, ErrorCode

_MONEY_RE = re.compile(r"^(0|[1-9][0-9]{0,19})$")                 # NUMERIC(20,0)
_QTY_RE = re.compile(r"^[0-9]{1,15}(\.[0-9]{1,3})?$")             # NUMERIC(18,3)
_BUNDLE_RE = re.compile(r"^(0|[1-9][0-9]{0,17})$")                # NUMERIC(18,0)
MAX_MONEY = 10**20                                                # exclusive bound of NUMERIC(20,0)
_PREC = 80


def _text(value, field: str, code: ErrorCode) -> str:
    # JSON numbers / booleans / null / containers are never accepted (no float round-trips).
    if not isinstance(value, str):
        raise AppError(code, details=[{"field": field, "reason": "MUST_BE_STRING"}])
    return normalize_digits(value.strip())


def parse_money(value, field: str = "amount") -> Decimal:
    s = _text(value, field, ErrorCode.INVALID_MONEY)
    if not _MONEY_RE.match(s):
        raise AppError(ErrorCode.INVALID_MONEY, details=[{"field": field, "reason": "INVALID_FORMAT"}])
    return Decimal(s)


def parse_quantity(value, field: str = "quantity") -> Decimal:
    """Format errors -> INVALID_MONEY (section 15 'money/quantity format'); value <= 0 -> VALIDATION_ERROR."""
    s = _text(value, field, ErrorCode.INVALID_MONEY)
    if not _QTY_RE.match(s):
        raise AppError(ErrorCode.INVALID_MONEY, details=[{"field": field, "reason": "INVALID_FORMAT"}])
    d = Decimal(s)
    if d <= 0:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": field, "reason": "MUST_BE_POSITIVE"}])
    return d


def parse_estimated_weight(value, field: str = "estimated_weight") -> Decimal | None:
    if value is None:
        return None
    s = _text(value, field, ErrorCode.INVALID_MONEY)
    if not _QTY_RE.match(s):
        raise AppError(ErrorCode.INVALID_MONEY, details=[{"field": field, "reason": "INVALID_FORMAT"}])
    return Decimal(s)


def parse_bundle_count(value, field: str = "bundle_count") -> Decimal:
    """A count, not money: every failure (including 19 digits) is VALIDATION_ERROR, never INVALID_MONEY."""
    s = _text(value, field, ErrorCode.VALIDATION_ERROR)
    if not _BUNDLE_RE.match(s):
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": field, "reason": "INVALID_FORMAT"}])
    return Decimal(s)


def line_total(quantity: Decimal, unit_price: Decimal, discount: Decimal, tax: Decimal) -> Decimal:
    """The contract formula, with the Service pre-checks of section 10. Inputs must already be parsed."""
    with localcontext() as ctx:
        ctx.prec = _PREC
        gross = quantity * unit_price
        if discount > gross:
            raise AppError(ErrorCode.AMOUNT_OUT_OF_RANGE,
                           details=[{"field": "discount_amount", "reason": "EXCEEDS_GROSS"}])
        total = (gross - discount + tax).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if total < 0 or total >= MAX_MONEY:
            raise AppError(ErrorCode.AMOUNT_OUT_OF_RANGE, details=[{"field": "line_total", "reason": "OUT_OF_RANGE"}])
        return total


@dataclass(frozen=True)
class Line:
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal


@dataclass(frozen=True)
class HeaderTotals:
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    grand_total: Decimal


def preview_header_totals(lines: Iterable[Line]) -> HeaderTotals:
    """Range PRE-CHECK only (section 10: each header total must fit 20 digits). Mirrors recompute_purchase_request_totals
    in 001; the Service never stores or returns these - totals are read back from the database."""
    sub = disc = tax = grand = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = _PREC
        for ln in lines:
            sub += (ln.quantity * ln.unit_price).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            disc += ln.discount_amount
            tax += ln.tax_amount
            grand += line_total(ln.quantity, ln.unit_price, ln.discount_amount, ln.tax_amount)
    t = HeaderTotals(sub, disc, tax, grand)
    for name in ("subtotal", "discount_total", "tax_total", "grand_total"):
        if getattr(t, name) >= MAX_MONEY:
            raise AppError(ErrorCode.AMOUNT_OUT_OF_RANGE, details=[{"field": name, "reason": "OUT_OF_RANGE"}])
    return t


def money_str(d: Decimal) -> str:
    """Integer string for JSON (section 10)."""
    return format(d.quantize(Decimal(1)), "f")
