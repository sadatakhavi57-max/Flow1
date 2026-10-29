"""Coarse role-based authorization - contract section 4 (D5). One matrix, deny by default."""
from __future__ import annotations

from enum import Enum

from .errors import AppError, ErrorCode


class Role(str, Enum):
    ADMIN = "ADMIN"
    SALES = "SALES"
    ACCOUNTING = "ACCOUNTING"


class Cap(str, Enum):
    ME = "me"
    ORG_READ = "organizations:read"
    LOOKUP_READ = "lookups:read"                      # product-categories, units (ADR-063)
    CUSTOMER_READ = "customers:read"
    CUSTOMER_WRITE = "customers:write"
    PRODUCT_READ = "products:read"                    # incl. GET /products/{id}/specifications
    PRODUCT_WRITE = "products:write"
    REQUEST_READ = "requests:read"                    # requests, items, pricing (read)
    REQUEST_CREATE = "requests:create"
    REQUEST_WRITE = "requests:write"                  # patch, items, pricing, submit, cancel - SALES: own requests only
    AUDIT_READ = "audit:read"
    # Stage 4 (contract section 26): pre-invoices. "own" = purchase_requests.created_by of the SOURCE request.
    PREINVOICE_READ = "pre_invoices:read"                    # list/get/pdf download; SALES: own source requests only
    PREINVOICE_CREATE = "pre_invoices:create"                # make a DRAFT; SALES: own source requests only
    PREINVOICE_ISSUE = "pre_invoices:issue"
    PREINVOICE_CANCEL_DRAFT = "pre_invoices:cancel_draft"    # SALES: own source requests only
    PREINVOICE_CANCEL_ISSUED = "pre_invoices:cancel_issued"
    PREINVOICE_PDF = "pre_invoices:pdf"                      # generate / retry the PDF


_ALL = set(Role)
MATRIX: dict[Cap, frozenset[Role]] = {
    Cap.ME: frozenset(_ALL),
    Cap.ORG_READ: frozenset(_ALL),
    Cap.LOOKUP_READ: frozenset(_ALL),
    Cap.CUSTOMER_READ: frozenset(_ALL),
    Cap.CUSTOMER_WRITE: frozenset({Role.ADMIN, Role.SALES}),
    Cap.PRODUCT_READ: frozenset(_ALL),
    Cap.PRODUCT_WRITE: frozenset({Role.ADMIN}),
    Cap.REQUEST_READ: frozenset(_ALL),
    Cap.REQUEST_CREATE: frozenset({Role.ADMIN, Role.SALES}),
    Cap.REQUEST_WRITE: frozenset({Role.ADMIN, Role.SALES}),
    Cap.AUDIT_READ: frozenset({Role.ADMIN}),
    Cap.PREINVOICE_READ: frozenset(_ALL),
    Cap.PREINVOICE_CREATE: frozenset({Role.ADMIN, Role.SALES}),
    Cap.PREINVOICE_ISSUE: frozenset({Role.ADMIN, Role.ACCOUNTING}),
    Cap.PREINVOICE_CANCEL_DRAFT: frozenset({Role.ADMIN, Role.SALES}),
    Cap.PREINVOICE_CANCEL_ISSUED: frozenset({Role.ADMIN, Role.ACCOUNTING}),
    Cap.PREINVOICE_PDF: frozenset({Role.ADMIN, Role.ACCOUNTING}),
}
assert set(MATRIX) == set(Cap)
OWN_ONLY = {Cap.REQUEST_WRITE: {Role.SALES},          # roles restricted to requests they created
            Cap.PREINVOICE_READ: {Role.SALES}, Cap.PREINVOICE_CREATE: {Role.SALES},
            Cap.PREINVOICE_CANCEL_DRAFT: {Role.SALES}}


def authorize(role_code: str, cap: Cap, *, caller_id: str | None = None, owner_id: str | None = None) -> None:
    """Raise FORBIDDEN_ROLE / FORBIDDEN_NOT_OWNER, else return. `owner_id` = purchase_requests.created_by.
    An unknown role code is denied everything (a role added to the database does not gain access by accident)."""
    try:
        role = Role(role_code)
    except ValueError:
        raise AppError(ErrorCode.FORBIDDEN_ROLE)
    if role not in MATRIX[cap]:
        raise AppError(ErrorCode.FORBIDDEN_ROLE)
    if role in OWN_ONLY.get(cap, ()):
        if caller_id is None or owner_id is None or str(caller_id).lower() != str(owner_id).lower():
            raise AppError(ErrorCode.FORBIDDEN_NOT_OWNER)


def has_capability(role_code: str, cap: Cap) -> bool:
    """True when the role may do `cap` at all (ownership is NOT considered). An unknown role has nothing."""
    try:
        return Role(role_code) in MATRIX[cap]
    except ValueError:
        return False


def is_own_only(role_code: str, cap: Cap) -> bool:
    """True when the role is restricted to the caller's own requests for `cap` (list queries filter instead of failing)."""
    try:
        return Role(role_code) in OWN_ONLY.get(cap, ())
    except ValueError:
        return True                       # unknown role: the most restrictive reading (it is denied by authorize() anyway)
