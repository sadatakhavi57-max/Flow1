"""Error codes and HTTP statuses - contract section 15 (single source of truth)."""
from __future__ import annotations
from enum import Enum


class ErrorCode(str, Enum):
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_REFRESH_INVALID = "AUTH_REFRESH_INVALID"
    FORBIDDEN_ROLE = "FORBIDDEN_ROLE"
    FORBIDDEN_NOT_OWNER = "FORBIDDEN_NOT_OWNER"
    NOT_FOUND = "NOT_FOUND"
    STATE_CONFLICT = "STATE_CONFLICT"
    STALE_UPDATE = "STALE_UPDATE"
    DUPLICATE_IDENTIFIER = "DUPLICATE_IDENTIFIER"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_MONEY = "INVALID_MONEY"
    AMOUNT_OUT_OF_RANGE = "AMOUNT_OUT_OF_RANGE"
    INACTIVE_REFERENCE = "INACTIVE_REFERENCE"
    REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"
    SPECIFICATION_INVALID = "SPECIFICATION_INVALID"
    SUBMIT_PRECONDITION_FAILED = "SUBMIT_PRECONDITION_FAILED"
    PDF_GENERATION_FAILED = "PDF_GENERATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"


HTTP_STATUS = {
    ErrorCode.MALFORMED_REQUEST: 400,
    ErrorCode.AUTH_INVALID_CREDENTIALS: 401,
    ErrorCode.AUTH_TOKEN_INVALID: 401,
    ErrorCode.AUTH_REFRESH_INVALID: 401,
    ErrorCode.FORBIDDEN_ROLE: 403,
    ErrorCode.FORBIDDEN_NOT_OWNER: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.STATE_CONFLICT: 409,
    ErrorCode.STALE_UPDATE: 409,
    ErrorCode.DUPLICATE_IDENTIFIER: 409,
    ErrorCode.DUPLICATE_RESOURCE: 409,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.INVALID_MONEY: 422,
    ErrorCode.AMOUNT_OUT_OF_RANGE: 422,
    ErrorCode.INACTIVE_REFERENCE: 422,
    ErrorCode.REFERENCE_NOT_FOUND: 422,
    ErrorCode.SPECIFICATION_INVALID: 422,
    ErrorCode.SUBMIT_PRECONDITION_FAILED: 422,
    ErrorCode.PDF_GENERATION_FAILED: 500,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.TEMPORARILY_UNAVAILABLE: 503,
}
assert set(HTTP_STATUS) == set(ErrorCode)

_DEFAULT_MESSAGE = {c: c.value.replace("_", " ").capitalize() for c in ErrorCode}


class AppError(Exception):
    """A business error that the HTTP layer renders as {"error": {code, message, details, request_id}}."""

    def __init__(self, code: ErrorCode, message: str | None = None, details=None, *, retryable: bool = False):
        self.code = code
        self.http_status = HTTP_STATUS[code]
        self.message = message or _DEFAULT_MESSAGE[code]
        self.details = details if details is not None else {}
        self.retryable = retryable
        super().__init__(f"{code.value}: {self.message}")

    def to_body(self, request_id: str) -> dict:
        return {"error": {"code": self.code.value, "message": self.message,
                          "details": self.details, "request_id": request_id}}


# ---------------------------------------------------------------- PostgreSQL error mapping (section 15)
_AMOUNT_CONSTRAINTS = {
    "chk_request_items_amounts", "chk_request_items_discount_not_exceed",
    "chk_request_items_line_total_consistency", "chk_purchase_requests_amounts",
    "chk_purchase_requests_grand_total_consistency",
}
_FIELD_CONSTRAINTS = {  # check name -> (field, reason) rendered under VALIDATION_ERROR
    "chk_purchase_requests_delivery_date": ("requested_delivery_date", "BEFORE_REQUEST_DATE"),
    "chk_request_items_quantity": ("quantity", "MUST_BE_POSITIVE"),
    "chk_request_items_bundle_count": ("bundle_count", "MUST_NOT_BE_NEGATIVE"),
    "chk_request_items_weight": ("estimated_weight", "MUST_NOT_BE_NEGATIVE"),
    "chk_customers_credit_limit": ("credit_limit", "MUST_NOT_BE_NEGATIVE"),
}
_CUSTOMER_IDENTIFIER_INDEXES = {
    "uq_customers_org_national_id": "national_id",
    "uq_customers_org_economic_code": "economic_code",
}
_PRE_INVOICE_INDEXES = {            # 004: reached only if two writers slip past the request-header lock (contract 14.2)
    "uq_pre_invoices_issued_per_request": "ACTIVE_PRE_INVOICE_EXISTS",
    "uq_pre_invoices_draft_per_request": "OPEN_DRAFT_EXISTS",
    "uq_pre_invoices_issued_per_chain": "ACTIVE_PRE_INVOICE_EXISTS",
    "uq_pre_invoices_one_successor": "ALREADY_REPLACED",
}
_RETRYABLE = {"40P01", "40001"}


def map_pg_error(sqlstate: str, constraint: str | None = None, message: str = "") -> AppError:
    """Map a PostgreSQL error to an AppError. Never echoes SQL text or the server message to the client.

    Specification-snapshot trigger errors (002) mean the Service built a bad snapshot, i.e. a bug:
    they become INTERNAL_ERROR rather than a misleading client error.
    """
    msg = message or ""
    if sqlstate == "55000":
        return AppError(ErrorCode.STATE_CONFLICT)
    if "specification snapshot" in msg:
        return AppError(ErrorCode.INTERNAL_ERROR)
    if sqlstate == "23505":
        if constraint in _CUSTOMER_IDENTIFIER_INDEXES:
            return AppError(ErrorCode.DUPLICATE_IDENTIFIER, details={"field": _CUSTOMER_IDENTIFIER_INDEXES[constraint]})
        if constraint == "uq_products_org_code":
            return AppError(ErrorCode.DUPLICATE_RESOURCE, details={"field": "code"})
        if constraint == "uq_products_org_name":
            return AppError(ErrorCode.DUPLICATE_RESOURCE, details={"field": "name"})
        if constraint in _PRE_INVOICE_INDEXES:
            return AppError(ErrorCode.DUPLICATE_RESOURCE, details={"reason": _PRE_INVOICE_INDEXES[constraint]})
        return AppError(ErrorCode.DUPLICATE_RESOURCE)
    if sqlstate == "23503":
        return AppError(ErrorCode.REFERENCE_NOT_FOUND)
    if sqlstate == "22003":
        return AppError(ErrorCode.AMOUNT_OUT_OF_RANGE)
    if sqlstate == "23514":
        if constraint in _AMOUNT_CONSTRAINTS:
            return AppError(ErrorCode.AMOUNT_OUT_OF_RANGE)
        if constraint in _FIELD_CONSTRAINTS:
            f, r = _FIELD_CONSTRAINTS[constraint]
            return AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": f, "reason": r}])
        return AppError(ErrorCode.INTERNAL_ERROR)
    if sqlstate in _RETRYABLE:
        return AppError(ErrorCode.TEMPORARILY_UNAVAILABLE, retryable=True)
    if sqlstate.startswith("08") or sqlstate in {"57P01", "57P02", "57P03", "53300"}:
        return AppError(ErrorCode.TEMPORARILY_UNAVAILABLE)
    return AppError(ErrorCode.INTERNAL_ERROR)
