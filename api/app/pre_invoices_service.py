"""Pre-invoices (Stage 4) - contract section 26.  One HTTP request = one transaction (14.1), EXCEPT the PDF generation, which is
three steps on purpose (see generate_pdf).  Every write on a pre-invoice takes the SOURCE REQUEST header lock first (14.2), then
the replaced document (if any), then the number counter (first version only), then the pre-invoice row.  Audit rows are written
in the same transaction as the change they describe (13); PDF failure audit is best-effort."""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from tradeflow_core import inputs
from tradeflow_core import pre_invoice as pi
from tradeflow_core import purchase_inputs as pin
from tradeflow_core.authz import Cap, authorize, has_capability, is_own_only
from tradeflow_core.errors import AppError, ErrorCode

from . import serialize
from .queries import like_pattern, not_found, page_args, write_audit

log = logging.getLogger("tradeflow.pdf")

_LOCK_REQUEST = "SELECT * FROM purchase_requests WHERE id = %s AND organization_id = %s FOR UPDATE"
_SOURCE_ITEMS = ("SELECT i.*, p.code AS product_code, p.name AS product_name, u.code AS unit_code, u.name AS unit_name"
                 " FROM purchase_request_items i JOIN products p ON p.id = i.product_id JOIN units u ON u.id = i.unit_id"
                 " WHERE i.purchase_request_id = %s AND i.organization_id = %s ORDER BY i.created_at ASC, i.id ASC")
_DOC_COLUMNS = ("id, organization_id, pre_invoice_id, status, pdf_sha256, pdf_size, template_version, generated_at,"
                " attempt_count, window_started_at, window_attempt_count, last_attempt_at, last_error_code")   # never pdf_data


def _conflict(reason: str, **extra) -> AppError:
    return AppError(ErrorCode.STATE_CONFLICT, details={"reason": reason, **extra})


class PreInvoiceService:
    def __init__(self, db, renderer=None, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.renderer, self.clock = db, renderer or pi.UnavailableRenderer(), clock

    # ------------------------------------------------------------------ loading helpers
    @staticmethod
    def _pre(conn, p, pid, lock=False):
        r = conn.execute("SELECT * FROM pre_invoices WHERE id = %s AND organization_id = %s" + (" FOR UPDATE" if lock else ""),
                         (pid, p.org_id)).fetchone()
        if r is None:
            raise not_found("pre_invoice")
        return r

    @staticmethod
    def _lock_request(conn, p, request_id):
        r = conn.execute(_LOCK_REQUEST, (request_id, p.org_id)).fetchone()
        if r is None:
            raise not_found("purchase_request")
        return r

    @staticmethod
    def _owner_id(conn, p, source_request_id) -> str | None:
        r = conn.execute("SELECT created_by FROM purchase_requests WHERE id = %s AND organization_id = %s",
                         (source_request_id, p.org_id)).fetchone()
        return None if r is None else str(r["created_by"])

    @staticmethod
    def _items(conn, p, pid):
        return conn.execute("SELECT * FROM pre_invoice_items WHERE pre_invoice_id = %s AND organization_id = %s ORDER BY line_no ASC",
                            (pid, p.org_id)).fetchall()

    @staticmethod
    def _doc(conn, p, pid, lock=False):
        return conn.execute(f"SELECT {_DOC_COLUMNS} FROM pre_invoice_documents WHERE pre_invoice_id = %s AND organization_id = %s"
                            + (" FOR UPDATE" if lock else ""), (pid, p.org_id)).fetchone()

    def _detail(self, conn, p, pid, row=None) -> dict:
        row = row or self._pre(conn, p, pid)
        d = serialize.pre_invoice(row, self._doc(conn, p, pid))
        d["items"] = [serialize.pre_invoice_item(i) for i in self._items(conn, p, pid)]
        return d

    # ------------------------------------------------------------------ create a DRAFT
    def create(self, p, request_id: str, body, ip: str) -> dict:
        request_id = inputs.parse_uuid(request_id, "id")
        supersedes_id = pi.parse_create(body)
        authorize(p.role_code, Cap.PREINVOICE_CREATE, caller_id=p.user_id, owner_id=p.user_id)     # role first

        def work(conn):
            req = self._lock_request(conn, p, request_id)                                          # 1) request header
            authorize(p.role_code, Cap.PREINVOICE_CREATE, caller_id=p.user_id, owner_id=str(req["created_by"]))
            if req["status"] != "SUBMITTED":
                raise _conflict("SOURCE_NOT_SUBMITTED", status=req["status"])
            live = {r["status"]: str(r["id"]) for r in conn.execute(
                "SELECT id, status FROM pre_invoices WHERE organization_id = %s AND source_request_id = %s"
                " AND status IN ('DRAFT', 'ISSUED')", (p.org_id, request_id)).fetchall()}
            if "ISSUED" in live:
                raise _conflict("ACTIVE_PRE_INVOICE_EXISTS", pre_invoice_id=live["ISSUED"])
            if "DRAFT" in live:
                raise _conflict("OPEN_DRAFT_EXISTS", pre_invoice_id=live["DRAFT"])

            prev = None
            if supersedes_id is not None:                                                          # 2) the document being replaced
                prev = conn.execute("SELECT * FROM pre_invoices WHERE id = %s AND organization_id = %s FOR UPDATE",
                                    (supersedes_id, p.org_id)).fetchone()
                if prev is None:
                    raise AppError(ErrorCode.REFERENCE_NOT_FOUND,
                                   details=[{"field": "supersedes_id", "reason": ErrorCode.REFERENCE_NOT_FOUND.value}])
                authorize(p.role_code, Cap.PREINVOICE_READ, caller_id=p.user_id,
                          owner_id=self._owner_id(conn, p, prev["source_request_id"]))
                if str(prev["source_request_id"]) == request_id:
                    raise inputs.verr("supersedes_id", "SAME_SOURCE_REQUEST")
                if prev["status"] != "ISSUED":
                    raise _conflict("NOT_ISSUED", status=prev["status"])

            seller = conn.execute("SELECT * FROM organizations WHERE id = %s", (p.org_id,)).fetchone()
            customer = conn.execute("SELECT * FROM customers WHERE id = %s AND organization_id = %s",
                                    (req["customer_id"], p.org_id)).fetchone()
            items = conn.execute(_SOURCE_ITEMS, (request_id, p.org_id)).fetchall()
            snap = pi.build_snapshot(seller, customer, req, items)

            pid = str(uuid.uuid4())
            chain_id = str(prev["chain_id"]) if prev else pid
            head = snap["header"]
            cols = ["id", "organization_id", "source_request_id", "chain_id", "supersedes_id", "created_by"] + list(head)
            vals = [pid, p.org_id, request_id, chain_id, None if prev is None else str(prev["id"]), p.user_id] + list(head.values())
            conn.execute(f"INSERT INTO pre_invoices ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", vals)   # cols: internal constants
            for it in snap["items"]:
                icols = ["organization_id", "pre_invoice_id"] + list(it)
                ivals = [p.org_id, pid] + [Jsonb(v) if k == "specifications" else v for k, v in it.items()]
                conn.execute(f"INSERT INTO pre_invoice_items ({', '.join(icols)}) VALUES ({', '.join(['%s'] * len(icols))})", ivals)
            write_audit(conn, p, "CREATE", "PRE_INVOICE", pid,
                        new=pi.audit_data(id=pid, status="DRAFT", source_request_id=request_id, request_number=req["request_number"],
                                          supersedes_id=None if prev is None else prev["id"], chain_id=chain_id,
                                          grand_total=req["grand_total"]), ip=ip)
            return self._detail(conn, p, pid)
        return self.db.run(work)

    # ------------------------------------------------------------------ read
    def list(self, p, query):
        authorize(p.role_code, Cap.PREINVOICE_READ, caller_id=p.user_id, owner_id=p.user_id)       # role only; ownership = a filter here
        page, size, offset = page_args(query)
        where, args = ["pi.organization_id = %s"], [p.org_id]
        if is_own_only(p.role_code, Cap.PREINVOICE_READ):
            where.append("r.created_by = %s"); args.append(p.user_id)
        st = query.get("status")
        if st is not None:
            if st not in {s.value for s in pi.PIStatus}:
                raise inputs.verr("status", "UNKNOWN_STATUS")
            where.append("pi.status = %s"); args.append(st)
        if query.get("source_request_id") is not None:
            where.append("pi.source_request_id = %s"); args.append(inputs.parse_uuid(query["source_request_id"], "source_request_id"))
        if query.get("customer_id") is not None:
            where.append("pi.customer_id = %s"); args.append(inputs.parse_uuid(query["customer_id"], "customer_id"))
        cf, ct = pin.parse_date_param(query.get("created_from"), "created_from"), pin.parse_date_param(query.get("created_to"), "created_to")
        if cf:
            where.append("pi.created_at >= (%s::date::timestamp AT TIME ZONE 'Asia/Tehran')"); args.append(cf)
        if ct:
            where.append("pi.created_at < ((%s::date + 1)::timestamp AT TIME ZONE 'Asia/Tehran')"); args.append(ct)
        term = inputs.text(query.get("search"), "search", 100)
        if term:
            where.append("(pi.pre_invoice_number ILIKE %s ESCAPE '\\' OR pi.request_number ILIKE %s ESCAPE '\\' OR pi.customer_name ILIKE %s ESCAPE '\\')")
            args += [like_pattern(term)] * 3
        w = " AND ".join(where)

        def work(conn):
            base = ("FROM pre_invoices pi JOIN purchase_requests r ON r.id = pi.source_request_id AND r.organization_id = pi.organization_id"
                    " LEFT JOIN pre_invoice_documents d ON d.pre_invoice_id = pi.id AND d.organization_id = pi.organization_id WHERE " + w)
            total = conn.execute("SELECT count(*) AS n " + base, args).fetchone()["n"]
            rows = conn.execute("SELECT pi.*, d.status AS pdf_status " + base + " ORDER BY pi.created_at DESC, pi.id DESC LIMIT %s OFFSET %s",
                                args + [size, offset]).fetchall()
            out = []
            for r in rows:
                x = serialize.pre_invoice(r)
                x["pdf"] = {"status": r["pdf_status"]} if r["pdf_status"] else None             # list rows carry the PDF status only
                out.append(x)
            return out, total
        items, total = self.db.run(work)
        return items, page, size, total

    def get(self, p, pid: str) -> dict:
        pid = inputs.parse_uuid(pid, "id")
        authorize(p.role_code, Cap.PREINVOICE_READ, caller_id=p.user_id, owner_id=p.user_id)

        def work(conn):
            row = self._pre(conn, p, pid)
            authorize(p.role_code, Cap.PREINVOICE_READ, caller_id=p.user_id, owner_id=self._owner_id(conn, p, row["source_request_id"]))
            return self._detail(conn, p, pid, row)
        return self.db.run(work)

    # ------------------------------------------------------------------ issue
    def issue(self, p, pid: str, ip: str) -> dict:
        pid = inputs.parse_uuid(pid, "id")
        authorize(p.role_code, Cap.PREINVOICE_ISSUE)

        def work(conn):
            pre0 = self._pre(conn, p, pid)                       # unlocked read: only to learn the source request / replaced document
            if pre0["status"] != "DRAFT":
                pi.assert_transition(pre0["status"], "ISSUED")
            req = self._lock_request(conn, p, str(pre0["source_request_id"]))                      # 1) request header
            prev = None
            if pre0["supersedes_id"] is not None:                                                  # 2) the replaced document
                prev = self._pre(conn, p, str(pre0["supersedes_id"]), lock=True)
            now = conn.execute("SELECT NOW() AS t").fetchone()["t"]
            number_seq = None
            if prev is None:                                                                       # 3) counter (first version only)
                number_seq = conn.execute("SELECT next_request_number(%s, %s) AS n",
                                          (p.org_id, pi.series_for_pre_invoice(now))).fetchone()["n"]
            row = self._pre(conn, p, pid, lock=True)                                               # 4) the pre-invoice
            pi.assert_transition(row["status"], "ISSUED")
            if req["status"] != "SUBMITTED":
                raise _conflict("SOURCE_NOT_SUBMITTED", status=req["status"])
            other = conn.execute("SELECT id FROM pre_invoices WHERE organization_id = %s AND source_request_id = %s"
                                 " AND status = 'ISSUED' AND id <> %s", (p.org_id, str(row["source_request_id"]), pid)).fetchone()
            if other is not None:
                raise _conflict("ACTIVE_PRE_INVOICE_EXISTS", pre_invoice_id=str(other["id"]))
            if prev is not None:
                if prev["status"] != "ISSUED":
                    raise _conflict("NOT_ISSUED", status=prev["status"])
                number, version = prev["pre_invoice_number"], prev["version"] + 1
                conn.execute("UPDATE pre_invoices SET status = 'SUPERSEDED', superseded_at = NOW() WHERE id = %s AND organization_id = %s",
                             (str(prev["id"]), p.org_id))
            else:
                number, version = pi.format_pre_invoice_number(pi.series_for_pre_invoice(now), number_seq), 1
            conn.execute("UPDATE pre_invoices SET status = 'ISSUED', pre_invoice_number = %s, version = %s, issued_by = %s,"
                         " issued_at = NOW() WHERE id = %s AND organization_id = %s", (number, version, p.user_id, pid, p.org_id))
            conn.execute("INSERT INTO pre_invoice_documents (organization_id, pre_invoice_id) VALUES (%s, %s)", (p.org_id, pid))
            write_audit(conn, p, "ISSUE", "PRE_INVOICE", pid, old=pi.audit_data(status="DRAFT"),
                        new=pi.audit_data(status="ISSUED", pre_invoice_number=number, version=version,
                                          grand_total=row["grand_total"], supersedes_id=None if prev is None else prev["id"]), ip=ip)
            if prev is not None:
                write_audit(conn, p, "SUPERSEDE", "PRE_INVOICE", str(prev["id"]), old=pi.audit_data(status="ISSUED"),
                            new=pi.audit_data(status="SUPERSEDED", superseded_by_id=pid), ip=ip)
            return self._detail(conn, p, pid)
        return self.db.run(work)

    # ------------------------------------------------------------------ cancel
    def cancel(self, p, pid: str, body, ip: str) -> dict:
        pid = inputs.parse_uuid(pid, "id")
        reason = pi.parse_cancel(body)
        if not (has_capability(p.role_code, Cap.PREINVOICE_CANCEL_DRAFT) or has_capability(p.role_code, Cap.PREINVOICE_CANCEL_ISSUED)):
            raise AppError(ErrorCode.FORBIDDEN_ROLE)

        def work(conn):
            pre0 = self._pre(conn, p, pid)
            req = self._lock_request(conn, p, str(pre0["source_request_id"]))                      # 1) request header
            row = self._pre(conn, p, pid, lock=True)                                               # 2) the pre-invoice
            st = row["status"]
            if st == "DRAFT":
                authorize(p.role_code, Cap.PREINVOICE_CANCEL_DRAFT, caller_id=p.user_id, owner_id=str(req["created_by"]))
            elif st == "ISSUED":
                authorize(p.role_code, Cap.PREINVOICE_CANCEL_ISSUED)
                if reason is None:
                    raise inputs.verr("reason", "REQUIRED")
            pi.assert_transition(st, "CANCELLED")
            conn.execute("UPDATE pre_invoices SET status = 'CANCELLED', cancelled_by = %s, cancelled_at = NOW(), cancel_reason = %s"
                         " WHERE id = %s AND organization_id = %s", (p.user_id, reason, pid, p.org_id))
            write_audit(conn, p, "CANCEL", "PRE_INVOICE", pid, old=pi.audit_data(status=st),
                        new=pi.audit_data(status="CANCELLED", pre_invoice_number=row["pre_invoice_number"], version=row["version"]),
                        description=reason, ip=ip)
            return self._detail(conn, p, pid)
        return self.db.run(work)

    # ------------------------------------------------------------------ PDF
    def generate_pdf(self, p, pid: str, ip: str) -> dict:
        """Generate (first attempt) or retry the PDF of an ISSUED/SUPERSEDED/CANCELLED pre-invoice - never touches the commercial status.

        Step 1 (transaction): lock the document row, return it if already 'ready' (idempotent), otherwise apply the attempt policy
        (core.pre_invoice.plan_attempt: RATE_LIMITED when refused) and COUNT the attempt, then commit.
        Step 2 (no transaction): render from the stored snapshot. A failure becomes a closed error code.
        Step 3 (transaction): lock the document row again and store 'ready' (bytes + SHA-256 + size + template version) or 'failed'
        (error code); a 'ready' document is never overwritten.  The audit row of a success is in the same transaction; the audit row
        of a failure is best-effort.  A PDF failure answers 500 PDF_GENERATION_FAILED after the failure has been recorded."""
        pid = inputs.parse_uuid(pid, "id")
        authorize(p.role_code, Cap.PREINVOICE_PDF)

        def start(conn):
            row = self._pre(conn, p, pid)
            if row["issued_at"] is None:
                raise _conflict("NOT_ISSUED", status=row["status"])
            doc = self._doc(conn, p, pid, lock=True)
            if doc is None:
                raise AppError(ErrorCode.INTERNAL_ERROR)                 # issue always creates the document row: a missing one is a bug
            if doc["status"] == pi.PDF_READY:
                return {"done": serialize.pre_invoice_document(doc)}
            plan = pi.plan_attempt(self.clock(), doc["attempt_count"], doc["window_started_at"], doc["window_attempt_count"], doc["last_attempt_at"])
            conn.execute("UPDATE pre_invoice_documents SET attempt_count = %s, window_started_at = %s, window_attempt_count = %s,"
                         " last_attempt_at = %s WHERE id = %s AND organization_id = %s",
                         (plan.attempt_count, plan.window_started_at, plan.window_attempt_count, plan.last_attempt_at, str(doc["id"]), p.org_id))
            return {"row": dict(row), "items": [dict(i) for i in self._items(conn, p, pid)], "attempt": plan.attempt_count}
        s = self.db.run(start)
        if "done" in s:
            return s["done"]

        data, code = None, None
        try:
            data = pi.check_pdf_output(self.renderer.render(pi.document_model(s["row"], s["items"])))
        except pi.PdfError as e:
            code = e.code
        except Exception as e:                                           # never log the message: it may carry document data
            log.error("pdf render failed pre_invoice=%s type=%s", pid, type(e).__name__)
            code = pi.PDF_RENDER_FAILED

        def finish(conn):
            doc = self._doc(conn, p, pid, lock=True)
            if doc["status"] == pi.PDF_READY:                            # a concurrent attempt finished first: keep it
                return serialize.pre_invoice_document(doc), None
            if code is None:
                sha = hashlib.sha256(data).hexdigest()
                conn.execute("UPDATE pre_invoice_documents SET status = 'ready', pdf_data = %s, pdf_sha256 = %s, pdf_size = %s,"
                             " template_version = %s, generated_at = NOW(), last_error_code = NULL"
                             " WHERE id = %s AND organization_id = %s AND status <> 'ready'",
                             (data, sha, len(data), pi.TEMPLATE_VERSION, str(doc["id"]), p.org_id))
                write_audit(conn, p, "PDF_GENERATE", "PRE_INVOICE", pid,
                            new=pi.audit_data(pdf_status="ready", pdf_size=len(data), pdf_sha256=sha,
                                              template_version=pi.TEMPLATE_VERSION, attempt_count=s["attempt"]), ip=ip)
            else:
                conn.execute("UPDATE pre_invoice_documents SET status = 'failed', last_error_code = %s"
                             " WHERE id = %s AND organization_id = %s AND status <> 'ready'", (code, str(doc["id"]), p.org_id))
                try:
                    with conn.transaction():                              # savepoint: an audit failure must not undo the 'failed' record
                        write_audit(conn, p, "PDF_FAIL", "PRE_INVOICE", pid,
                                    new=pi.audit_data(pdf_status="failed", error_code=code, attempt_count=s["attempt"]), ip=ip)
                except Exception as e:
                    log.error("pdf failure audit not written pre_invoice=%s type=%s", pid, type(e).__name__)
            return serialize.pre_invoice_document(self._doc(conn, p, pid)), code
        meta, failed = self.db.run(finish)
        if failed:
            raise AppError(ErrorCode.PDF_GENERATION_FAILED, details={"error_code": failed, "pdf": meta})
        return meta

    def download_pdf(self, p, pid: str):
        """-> (filename, bytes, sha256).  The only place the PDF bytes are read."""
        pid = inputs.parse_uuid(pid, "id")
        authorize(p.role_code, Cap.PREINVOICE_READ, caller_id=p.user_id, owner_id=p.user_id)

        def work(conn):
            row = self._pre(conn, p, pid)
            authorize(p.role_code, Cap.PREINVOICE_READ, caller_id=p.user_id, owner_id=self._owner_id(conn, p, row["source_request_id"]))
            d = conn.execute("SELECT status, pdf_data, pdf_sha256 FROM pre_invoice_documents WHERE pre_invoice_id = %s AND organization_id = %s",
                             (pid, p.org_id)).fetchone()
            if d is None or d["status"] != pi.PDF_READY:
                raise _conflict("PDF_NOT_READY", pdf_status=None if d is None else d["status"])
            return f"{row['pre_invoice_number']}-v{row['version']}.pdf", bytes(d["pdf_data"]), d["pdf_sha256"]
        return self.db.run(work)
