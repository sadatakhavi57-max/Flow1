"""Pre-invoice (Stage 4) - contract section 26, ADR-060, ADR-057.  Pure logic: no database, no HTTP.

What lives here
  * the status machine (DRAFT -> ISSUED | CANCELLED, ISSUED -> SUPERSEDED | CANCELLED; the last two are final);
  * the number: series 'PI-<jalali year>' in the EXISTING counter table of ADR-057, text 'PI-<year>-<n:06d>';
  * the PDF retry policy and the closed set of operational PDF error codes;
  * the snapshot (which request/customer/seller/item columns are copied) and the audit allow-list;
  * the neutral document model a PDF renderer receives, and the renderer interface.

MVP policy vs product rules: everything that is business policy of THIS slice (24-hour validity, prepayment, manager
approval, payment terms, printed fields) is deliberately absent - the core has no such rule and none is configurable yet.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from . import inputs, numbering
from .errors import AppError, ErrorCode
from .state import validate_cancel_reason


# ----------------------------------------------------------------------------------------------- status machine
class PIStatus(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"


ALLOWED_TRANSITIONS = frozenset({
    (PIStatus.DRAFT, PIStatus.ISSUED), (PIStatus.DRAFT, PIStatus.CANCELLED),
    (PIStatus.ISSUED, PIStatus.SUPERSEDED), (PIStatus.ISSUED, PIStatus.CANCELLED),
})
FINAL_STATUSES = frozenset({PIStatus.SUPERSEDED, PIStatus.CANCELLED})


def assert_transition(current: str, new: str) -> None:
    """Exactly the database rules of 004 (SQLSTATE 55000 there); the API reports STATE_CONFLICT."""
    try:
        pair = (PIStatus(current), PIStatus(new))
    except ValueError:
        raise AppError(ErrorCode.STATE_CONFLICT)
    if pair not in ALLOWED_TRANSITIONS:
        raise AppError(ErrorCode.STATE_CONFLICT, details={"from": pair[0].value, "to": pair[1].value})


# ----------------------------------------------------------------------------------------------- numbering (ADR-057)
_SERIES_RE = re.compile(r"^PI-(1[0-9]{3})$")
_NUMBER_RE = re.compile(r"^PI-(1[0-9]{3})-([0-9]{6,})$")


def series_for_pre_invoice(issued_at: datetime) -> str:
    """'PI-<jalali year of the ISSUE instant, Asia/Tehran>' - the series value passed to next_request_number()."""
    return "PI-" + numbering.series_for(issued_at)


def format_pre_invoice_number(series: str, n: int) -> str:
    if not _SERIES_RE.fullmatch(series):
        raise ValueError("series must be 'PI-' followed by a 4-digit Jalali year")
    if n < 1:
        raise ValueError("sequence numbers start at 1")
    return f"{series}-{n:06d}"


def parse_pre_invoice_number(s: str) -> tuple[str, int]:
    m = _NUMBER_RE.match(s)
    if not m:
        raise ValueError(f"not a pre-invoice number: {s!r}")
    return f"PI-{m.group(1)}", int(m.group(2))


# ----------------------------------------------------------------------------------------------- PDF policy
MAX_PDF_BYTES = 10 * 1024 * 1024
TEMPLATE_VERSION = "pi-1"
MIN_RETRY_INTERVAL_SECONDS = 60
MAX_RETRIES_PER_WINDOW = 3
RETRY_WINDOW_SECONDS = 15 * 60

PDF_PENDING, PDF_READY, PDF_FAILED = "pending", "ready", "failed"

# closed set of operational error codes stored in pre_invoice_documents.last_error_code
PDF_RENDERER_UNAVAILABLE = "PDF_RENDERER_UNAVAILABLE"
PDF_RENDER_FAILED = "PDF_RENDER_FAILED"
PDF_TOO_LARGE = "PDF_TOO_LARGE"
PDF_INVALID_OUTPUT = "PDF_INVALID_OUTPUT"
PDF_ERROR_CODES = frozenset({PDF_RENDERER_UNAVAILABLE, PDF_RENDER_FAILED, PDF_TOO_LARGE, PDF_INVALID_OUTPUT})


@dataclass(frozen=True)
class AttemptPlan:
    attempt_count: int
    window_started_at: datetime | None
    window_attempt_count: int
    last_attempt_at: datetime
    is_retry: bool


def plan_attempt(now: datetime, attempt_count: int, window_started_at: datetime | None,
                 window_attempt_count: int, last_attempt_at: datetime | None) -> AttemptPlan:
    """Decide whether a PDF generation attempt may start NOW, and what the counters become.

    Counting (one definition, used by the code, the tests and the documents):
      * the INITIAL attempt is the first attempt ever made for a document (attempt_count == 0). It is always allowed and
        is not a retry: it does not touch the retry window;
      * every later attempt is a RETRY. A retry needs MIN_RETRY_INTERVAL_SECONDS (60 s) since the previous attempt of any kind;
      * retries are counted in fixed windows of RETRY_WINDOW_SECONDS (15 min). A window starts at its first retry; when 15
        minutes have passed since it started, the next retry opens a new window. At most MAX_RETRIES_PER_WINDOW (3)
        retries fit in a window.  So the first 15-minute period can hold 1 initial + 3 retries = 4 attempts.
    A refused attempt raises RATE_LIMITED with details.retry_after (whole seconds >= 1); nothing is counted.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if attempt_count == 0:
        return AttemptPlan(1, window_started_at, window_attempt_count, now, False)
    if last_attempt_at is not None:
        wait = (last_attempt_at + timedelta(seconds=MIN_RETRY_INTERVAL_SECONDS) - now).total_seconds()
        if wait > 0:
            raise _limited(wait)
    started, count = window_started_at, window_attempt_count
    if started is None or now >= started + timedelta(seconds=RETRY_WINDOW_SECONDS):
        started, count = now, 0
    if count >= MAX_RETRIES_PER_WINDOW:
        raise _limited((started + timedelta(seconds=RETRY_WINDOW_SECONDS) - now).total_seconds())
    return AttemptPlan(attempt_count + 1, started, count + 1, now, True)


def _limited(seconds: float) -> AppError:
    retry = max(1, math.ceil(seconds))
    e = AppError(ErrorCode.RATE_LIMITED, details={"retry_after": retry})
    e.retry_after = retry
    return e


def check_pdf_output(data: Any) -> bytes:
    """What a renderer returned must be PDF bytes within the size cap; otherwise a closed error code (never a client error)."""
    if not isinstance(data, (bytes, bytearray)) or not data.startswith(b"%PDF-"):
        raise PdfError(PDF_INVALID_OUTPUT)
    if len(data) > MAX_PDF_BYTES:
        raise PdfError(PDF_TOO_LARGE)
    return bytes(data)


class PdfError(Exception):
    def __init__(self, code: str):
        if code not in PDF_ERROR_CODES:
            raise ValueError(f"unknown PDF error code {code!r}")
        self.code = code
        super().__init__(code)


class RendererUnavailable(PdfError):
    def __init__(self):
        super().__init__(PDF_RENDERER_UNAVAILABLE)


class PdfRenderer(Protocol):
    """The one thing the Service needs from a PDF library. The document model is plain data (see document_model)."""
    def render(self, model: dict) -> bytes: ...


class UnavailableRenderer:
    """Default until the owner approves a PDF library and a Persian (RTL) font: every attempt fails with a closed code, so the
    commercial document is unaffected and the failure is visible and retryable."""
    def render(self, model: dict) -> bytes:
        raise RendererUnavailable()


# ----------------------------------------------------------------------------------------------- inputs
def parse_create(body) -> str | None:
    """POST /purchase-requests/{id}/pre-invoices.
    Accept an optional canonical lowercase UUID in supersedes_id.
    """
    inputs.strict_object(body, ("supersedes_id",))
    value = body.get("supersedes_id")
    if value is None:
        return None
    parsed = inputs.parse_uuid(value, "supersedes_id")
    if parsed != value:
        raise inputs.verr("supersedes_id", "NOT_A_UUID")
    return parsed

def parse_cancel(body) -> str | None:
    """The reason is optional here; the Service requires it for an ISSUED pre-invoice (DRAFT: optional)."""
    inputs.strict_object(body, ("reason",))
    r = body.get("reason")
    return None if r is None else validate_cancel_reason(r)


# ----------------------------------------------------------------------------------------------- snapshot
SELLER_COLUMNS = ("name", "legal_name", "national_id", "economic_code", "registration_number", "phone", "email",
                  "address", "postal_code")
CUSTOMER_COLUMNS = ("type", "name", "national_id", "economic_code", "registration_number", "mobile", "phone", "email",
                    "address", "postal_code")            # credit_limit is NOT copied
ITEM_COLUMNS = ("quantity", "bundle_count", "estimated_weight", "unit_price", "discount_amount", "tax_amount",
                "line_total", "notes")


def build_snapshot(seller: dict, customer: dict, request: dict, items: list[dict]) -> dict:
    """Rows (dict-like) -> the column values of one pre_invoices row and its pre_invoice_items rows.
    Nothing is computed: money and quantities are copied exactly as the request holds them."""
    header = {
        "request_number": request["request_number"], "request_date": request["request_date"],
        "requested_delivery_date": request["requested_delivery_date"], "request_notes": request["notes"],
        "customer_id": customer["id"],
        "subtotal": request["subtotal"], "discount_total": request["discount_total"],
        "tax_total": request["tax_total"], "grand_total": request["grand_total"],
    }
    header.update({f"seller_{c}": seller[c] for c in SELLER_COLUMNS})
    header.update({f"customer_{c}": customer["customer_type" if c == "type" else c] for c in CUSTOMER_COLUMNS})
    rows = []
    for n, it in enumerate(items, start=1):
        r = {"line_no": n, "source_item_id": it["id"], "product_id": it["product_id"], "product_code": it["product_code"],
             "product_name": it["product_name"], "unit_id": it["unit_id"], "unit_code": it["unit_code"],
             "unit_name": it["unit_name"], "specifications": it["specifications"]}
        r.update({c: it[c] for c in ITEM_COLUMNS})
        rows.append(r)
    return {"header": header, "items": rows}


# ----------------------------------------------------------------------------------------------- audit allow-list
AUDIT_KEYS = frozenset({
    "id", "pre_invoice_number", "version", "status", "source_request_id", "request_number", "supersedes_id", "chain_id",
    "superseded_by_id", "grand_total", "pdf_status", "pdf_size", "pdf_sha256", "template_version", "error_code",
    "attempt_count",
})


def audit_data(**fields) -> dict:
    """The ONLY way pre-invoice audit payloads are made. Customer/seller data, notes and items are never audited:
    a key outside the allow-list is a programming error (ValueError), not a client error."""
    bad = sorted(set(fields) - AUDIT_KEYS)
    if bad:
        raise ValueError(f"not allowed in pre-invoice audit data: {bad}")
    return {k: (str(v) if v is not None and not isinstance(v, (int, bool)) else v) for k, v in fields.items()}


# ----------------------------------------------------------------------------------------------- document model
def document_model(pi: dict, items: list[dict]) -> dict:
    """The neutral model a renderer draws: the pre-invoice row and its item rows (dicts, as stored in the snapshot).
    It contains the snapshot only - never the current customer/product/organization and NOT the lifecycle status - so the
    same stored snapshot always yields the same content (a renderer may differ only in layout)."""
    return {
        "template_version": TEMPLATE_VERSION,
        "number": pi["pre_invoice_number"], "version": pi["version"], "issued_at": pi["issued_at"],
        "request": {"number": pi["request_number"], "date": pi["request_date"],
                    "delivery_date": pi["requested_delivery_date"], "notes": pi["request_notes"]},
        "seller": {c: pi[f"seller_{c}"] for c in SELLER_COLUMNS},
        "customer": {c: pi[f"customer_{c}"] for c in CUSTOMER_COLUMNS},
        "items": [{"line_no": i["line_no"], "product_code": i["product_code"], "product_name": i["product_name"],
                   "unit_code": i["unit_code"], "unit_name": i["unit_name"],
                   **{c: i[c] for c in ITEM_COLUMNS}, "specifications": i["specifications"]} for i in items],
        "totals": {"subtotal": pi["subtotal"], "discount_total": pi["discount_total"],
                   "tax_total": pi["tax_total"], "grand_total": pi["grand_total"]},
    }
