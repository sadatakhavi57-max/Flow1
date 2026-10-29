"""Stage 4 pure logic (no database): status machine, number, PDF attempt policy, PDF output checks, snapshot, audit allow-list,
input parsing, document model, error mapping of the 004 unique indexes.  WRITTEN, NOT YET RUN by its author."""
import itertools
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from tradeflow_core import pre_invoice as pi
from tradeflow_core.errors import AppError, ErrorCode, HTTP_STATUS, map_pg_error

T0 = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)


def code_of(fn, *a, **k):
    try:
        fn(*a, **k)
    except AppError as e:
        return e.code
    except pi.PdfError as e:
        return e.code
    return None


class StatusMachine(unittest.TestCase):
    def test_all_sixteen_pairs(self):
        allowed = {("DRAFT", "ISSUED"), ("DRAFT", "CANCELLED"), ("ISSUED", "SUPERSEDED"), ("ISSUED", "CANCELLED")}
        names = ["DRAFT", "ISSUED", "SUPERSEDED", "CANCELLED"]
        for a, b in itertools.product(names, repeat=2):
            got = code_of(pi.assert_transition, a, b)
            self.assertEqual(got is None, (a, b) in allowed, (a, b))
            if (a, b) not in allowed:
                self.assertEqual(got, ErrorCode.STATE_CONFLICT)

    def test_final_states_and_unknown_values(self):
        self.assertEqual(pi.FINAL_STATUSES, frozenset({pi.PIStatus.SUPERSEDED, pi.PIStatus.CANCELLED}))
        for s in ("SUPERSEDED", "CANCELLED"):
            for t in ("DRAFT", "ISSUED", "SUPERSEDED", "CANCELLED"):
                self.assertEqual(code_of(pi.assert_transition, s, t), ErrorCode.STATE_CONFLICT)
        self.assertEqual(code_of(pi.assert_transition, "DRAFT", "DONE"), ErrorCode.STATE_CONFLICT)
        self.assertEqual(code_of(pi.assert_transition, "draft", "ISSUED"), ErrorCode.STATE_CONFLICT)       # case-sensitive


class Numbering(unittest.TestCase):
    def test_series_uses_the_jalali_year_of_the_issue_instant(self):
        self.assertEqual(pi.series_for_pre_invoice(datetime(2026, 10, 29, tzinfo=timezone.utc)), "PI-1405")
        self.assertEqual(pi.series_for_pre_invoice(datetime(2026, 3, 20, 12, tzinfo=timezone.utc)), "PI-1404")     # before Nowruz 1405
        self.assertEqual(pi.series_for_pre_invoice(datetime(2026, 3, 21, 12, tzinfo=timezone.utc)), "PI-1405")

    def test_format_and_parse_roundtrip(self):
        self.assertEqual(pi.format_pre_invoice_number("PI-1405", 1), "PI-1405-000001")
        self.assertEqual(pi.format_pre_invoice_number("PI-1405", 1234567), "PI-1405-1234567")      # grows beyond six digits
        self.assertEqual(pi.parse_pre_invoice_number("PI-1405-000042"), ("PI-1405", 42))
        for s, n in [("PI-1405", 1), ("PI-1405", 999999), ("PI-1499", 12)]:
            self.assertEqual(pi.parse_pre_invoice_number(pi.format_pre_invoice_number(s, n)), (s, n))

    def test_bad_values_are_rejected(self):
        for bad in ("1405", "PI-140", "PI-14055", "pi-1405", "PI-1405-1", "RQ-1405"):
            with self.assertRaises(ValueError, msg=bad):
                pi.format_pre_invoice_number(bad, 1)
        with self.assertRaises(ValueError):
            pi.format_pre_invoice_number("PI-1405", 0)
        for bad in ("PI-1405-1", "1405-000001", "PI-1405-0000a1", ""):
            with self.assertRaises(ValueError, msg=bad):
                pi.parse_pre_invoice_number(bad)

    def test_the_request_series_is_not_touched(self):
        from tradeflow_core import numbering
        self.assertEqual(numbering.series_for(datetime(2026, 10, 29, tzinfo=timezone.utc)), "1405")      # unchanged: no 'PI-' prefix


class AttemptPolicy(unittest.TestCase):
    """One definition: the initial attempt is not a retry; retries need >= 60 s; at most 3 retries per fixed 15-minute window."""

    def plan(self, now, st):
        return pi.plan_attempt(now, st["n"], st["ws"], st["wc"], st["last"])

    def run_seq(self, offsets):
        """offsets in seconds from T0; returns a list of 'ok'/<retry_after> and the final counters"""
        st, out = {"n": 0, "ws": None, "wc": 0, "last": None}, []
        for o in offsets:
            now = T0 + timedelta(seconds=o)
            try:
                p = self.plan(now, st)
            except AppError as e:
                self.assertEqual(e.code, ErrorCode.RATE_LIMITED)
                out.append(e.details["retry_after"])
                continue
            st = {"n": p.attempt_count, "ws": p.window_started_at, "wc": p.window_attempt_count, "last": p.last_attempt_at}
            out.append("ok")
        return out, st

    def test_constants(self):
        self.assertEqual((pi.MIN_RETRY_INTERVAL_SECONDS, pi.MAX_RETRIES_PER_WINDOW, pi.RETRY_WINDOW_SECONDS, pi.MAX_PDF_BYTES),
                         (60, 3, 900, 10 * 1024 * 1024))

    def test_initial_attempt_is_free_and_not_a_retry(self):
        p = pi.plan_attempt(T0, 0, None, 0, None)
        self.assertEqual((p.attempt_count, p.window_started_at, p.window_attempt_count, p.is_retry), (1, None, 0, False))

    def test_sixty_second_boundary(self):
        out, _ = self.run_seq([0, 59, 60])
        self.assertEqual(out[0], "ok")
        self.assertEqual(out[1], 1)                                     # 59 s after the initial attempt: 1 s to wait
        self.assertEqual(out[2], "ok")                                  # exactly 60 s: allowed (a retry)

    def test_refusal_reports_whole_seconds_rounded_up(self):
        st = pi.plan_attempt(T0, 0, None, 0, None)
        with self.assertRaises(AppError) as cm:
            pi.plan_attempt(T0 + timedelta(seconds=10, milliseconds=1), st.attempt_count, None, 0, st.last_attempt_at)
        self.assertEqual(cm.exception.details["retry_after"], 50)
        self.assertEqual(cm.exception.retry_after, 50)

    def test_one_initial_plus_three_retries_in_the_first_window(self):
        out, st = self.run_seq([0, 60, 120, 180, 240])                  # initial, retry 1, 2, 3, then a 4th retry
        self.assertEqual(out[:4], ["ok"] * 4)
        self.assertIsInstance(out[4], int)                              # refused
        self.assertEqual(out[4], 960 - 240)                             # the window opened at the first retry (t=60) ends at t=960
        self.assertEqual((st["n"], st["wc"]), (4, 3))                   # a refused attempt is not counted

    def test_window_started_at_first_retry_and_reopens_after_15_minutes(self):
        # window starts at the first RETRY (t=60), so it ends at t=960
        out, st = self.run_seq([0, 60, 120, 180, 959, 960])
        self.assertEqual(out[:4], ["ok"] * 4)
        self.assertEqual(out[4], 1)                                     # t=959: window still open, 1 s left
        self.assertEqual(out[5], "ok")                                  # t=960: new window, retry counted as 1
        self.assertEqual((st["n"], st["wc"]), (5, 1))
        self.assertEqual(st["ws"], T0 + timedelta(seconds=960))

    def test_refusal_inside_window_reports_time_until_window_end(self):
        out, _ = self.run_seq([0, 60, 120, 180, 300])
        self.assertEqual(out[4], 960 - 300)

    def test_spacing_has_priority_over_the_window(self):
        out, _ = self.run_seq([0, 60, 120, 180, 181])
        self.assertEqual(out[4], 59)                                    # the 60 s rule is reported, not the window

    def test_naive_datetime_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            pi.plan_attempt(datetime(2026, 1, 1), 0, None, 0, None)

    def test_counters_stay_consistent_with_the_database_check(self):
        # chk_pre_invoice_documents_attempts: window_attempt_count <= attempt_count
        st = {"n": 0, "ws": None, "wc": 0, "last": None}
        for o in range(0, 20000, 61):
            try:
                p = self.plan(T0 + timedelta(seconds=o), st)
            except AppError:
                continue
            st = {"n": p.attempt_count, "ws": p.window_started_at, "wc": p.window_attempt_count, "last": p.last_attempt_at}
            self.assertLessEqual(st["wc"], st["n"])
            self.assertLessEqual(st["wc"], pi.MAX_RETRIES_PER_WINDOW)


class PdfOutput(unittest.TestCase):
    def test_valid_pdf_bytes_pass(self):
        self.assertEqual(pi.check_pdf_output(b"%PDF-1.7\n..."), b"%PDF-1.7\n...")
        self.assertEqual(pi.check_pdf_output(bytearray(b"%PDF-1.4")), b"%PDF-1.4")
        self.assertIsInstance(pi.check_pdf_output(bytearray(b"%PDF-1.4")), bytes)

    def test_size_cap_is_exactly_ten_mebibytes(self):
        ok = b"%PDF-" + b"x" * (pi.MAX_PDF_BYTES - 5)
        self.assertEqual(len(pi.check_pdf_output(ok)), pi.MAX_PDF_BYTES)
        self.assertEqual(code_of(pi.check_pdf_output, ok + b"x"), pi.PDF_TOO_LARGE)

    def test_not_a_pdf(self):
        for bad in (b"", b"PDF-", b"<html>", "%PDF-1.7", None, 5, b" %PDF-1.7"):
            self.assertEqual(code_of(pi.check_pdf_output, bad), pi.PDF_INVALID_OUTPUT, repr(bad))

    def test_error_codes_are_closed_and_match_the_database_regex(self):
        import re
        self.assertEqual(pi.PDF_ERROR_CODES, {"PDF_RENDERER_UNAVAILABLE", "PDF_RENDER_FAILED", "PDF_TOO_LARGE", "PDF_INVALID_OUTPUT"})
        for c in pi.PDF_ERROR_CODES:
            self.assertRegex(c, r"^[A-Z][A-Z0-9_]{0,49}$")                # chk_pre_invoice_documents_error_code
        with self.assertRaises(ValueError):
            pi.PdfError("SOMETHING_ELSE")

    def test_default_renderer_fails_with_a_closed_code(self):
        self.assertEqual(code_of(pi.UnavailableRenderer().render, {}), pi.PDF_RENDERER_UNAVAILABLE)
        self.assertEqual(HTTP_STATUS[ErrorCode.PDF_GENERATION_FAILED], 500)


def _rows():
    seller = {"name": "Seller", "legal_name": "Seller LLC", "national_id": "1", "economic_code": "2", "registration_number": "3",
              "phone": "021", "email": "s@x.ir", "address": "Tehran", "postal_code": "111"}
    customer = {"id": "c1", "customer_type": "COMPANY", "name": "Buyer", "national_id": "9", "economic_code": None,
                "registration_number": None, "mobile": "0912", "phone": None, "email": None, "address": "Isfahan",
                "postal_code": None, "credit_limit": D("5000000")}
    request = {"request_number": "1405-000007", "request_date": T0, "requested_delivery_date": None, "notes": "n",
               "subtotal": D("100"), "discount_total": D("10"), "tax_total": D("5"), "grand_total": D("95")}
    items = [{"id": "i1", "product_id": "p1", "product_code": "P-1", "product_name": "Pipe", "unit_id": "u1", "unit_code": "KG",
              "unit_name": "Kilogram", "quantity": D("10.000"), "bundle_count": D("1"), "estimated_weight": None,
              "unit_price": D("10"), "discount_amount": D("10"), "tax_amount": D("5"), "line_total": D("95"), "notes": None,
              "specifications": [{"field_code": "X", "value": "1"}]}]
    return seller, customer, request, items


class Snapshot(unittest.TestCase):
    def test_header_and_items_are_copied_not_computed(self):
        s, c, r, it = _rows()
        snap = pi.build_snapshot(s, c, r, it)
        h = snap["header"]
        self.assertEqual((h["subtotal"], h["discount_total"], h["tax_total"], h["grand_total"]), (D("100"), D("10"), D("5"), D("95")))
        self.assertEqual((h["request_number"], h["request_notes"], h["customer_id"], h["customer_type"], h["customer_name"]),
                         ("1405-000007", "n", "c1", "COMPANY", "Buyer"))
        self.assertEqual((h["seller_name"], h["seller_legal_name"], h["seller_postal_code"]), ("Seller", "Seller LLC", "111"))
        self.assertNotIn("customer_credit_limit", h)
        self.assertFalse([k for k in h if "credit" in k])
        row = snap["items"][0]
        self.assertEqual((row["line_no"], row["source_item_id"], row["product_code"], row["unit_code"], row["line_total"]), (1, "i1", "P-1", "KG", D("95")))
        self.assertEqual(row["specifications"], it[0]["specifications"])

    def test_columns_match_the_migration(self):
        import re
        from pathlib import Path
        sql = (Path(__file__).resolve().parents[2] / "db" / "sql" / "004_pre_invoices.sql")
        if not sql.is_file():
            self.skipTest("SKIPPED: 004_pre_invoices.sql not found")
        text = sql.read_text(encoding="utf-8")
        head = text.split("CREATE TABLE pre_invoice_items", 1)[0]
        items = text.split("CREATE TABLE pre_invoice_items", 1)[1].split("CREATE TABLE pre_invoice_documents", 1)[0]
        s, c, r, it = _rows()
        snap = pi.build_snapshot(s, c, r, it)
        for col in snap["header"]:
            self.assertIn(f"    {col} ", head, f"pre_invoices.{col}")
        for col in snap["items"][0]:
            self.assertIn(f"    {col} ", items, f"pre_invoice_items.{col}")

    def test_line_numbers_follow_input_order(self):
        s, c, r, it = _rows()
        two = it + [dict(it[0], id="i2")]
        self.assertEqual([x["line_no"] for x in pi.build_snapshot(s, c, r, two)["items"]], [1, 2])


class AuditAllowList(unittest.TestCase):
    def test_allowed_keys_work_and_values_are_plain(self):
        d = pi.audit_data(status="ISSUED", version=1, grand_total=D("95"), id="abc", supersedes_id=None)
        self.assertEqual(d, {"status": "ISSUED", "version": 1, "grand_total": "95", "id": "abc", "supersedes_id": None})

    def test_anything_else_is_a_programming_error(self):
        for k in ("customer_name", "customer_mobile", "customer_address", "seller_name", "request_notes", "notes", "items",
                  "password_hash", "credit_limit", "cancel_reason", "pdf_data"):
            with self.assertRaises(ValueError, msg=k):
                pi.audit_data(**{k: "x"})

    def test_allow_list_has_no_personal_or_item_data(self):
        for k in pi.AUDIT_KEYS:
            for bad in ("customer", "seller", "mobile", "email", "address", "phone", "notes", "items", "reason", "data"):
                self.assertNotIn(bad, k, k)


class Inputs(unittest.TestCase):
    ID = "5b0c8f2e-3f0a-4f0e-9c52-0d1f1a2b3c4d"

    def test_parse_create(self):
        self.assertIsNone(pi.parse_create({}))
        self.assertIsNone(pi.parse_create({"supersedes_id": None}))
        self.assertEqual(pi.parse_create({"supersedes_id": self.ID}), self.ID)
        for bad in ([], None, "x", {"supersedes_id": "nope"}, {"supersedes_id": self.ID.upper()}, {"supersedes_id": 5}, {"other": 1}, {"supersedes_id": self.ID, "x": 1}):
            self.assertEqual(code_of(pi.parse_create, bad), ErrorCode.VALIDATION_ERROR, repr(bad))

    def test_parse_cancel(self):
        self.assertIsNone(pi.parse_cancel({}))
        self.assertIsNone(pi.parse_cancel({"reason": None}))
        self.assertEqual(pi.parse_cancel({"reason": "  mistake "}), "mistake")
        self.assertEqual(len(pi.parse_cancel({"reason": "x" * 500})), 500)
        for bad in ("", "   ", "x" * 501, 5, ["a"]):
            self.assertEqual(code_of(pi.parse_cancel, {"reason": bad}), ErrorCode.VALIDATION_ERROR, repr(bad))
        for bad in ([], None, {"reason": "a", "extra": 1}):
            self.assertEqual(code_of(pi.parse_cancel, bad), ErrorCode.VALIDATION_ERROR, repr(bad))


class DocumentModel(unittest.TestCase):
    def test_model_is_the_snapshot_only(self):
        s, c, r, it = _rows()
        snap = pi.build_snapshot(s, c, r, it)
        row = {**snap["header"], "pre_invoice_number": "PI-1405-000001", "version": 2, "issued_at": T0, "status": "CANCELLED"}
        items = [{**snap["items"][0]}]
        m = pi.document_model(row, items)
        self.assertEqual((m["number"], m["version"], m["template_version"]), ("PI-1405-000001", 2, pi.TEMPLATE_VERSION))
        self.assertNotIn("status", m)
        self.assertNotIn("credit_limit", repr(m))
        self.assertEqual(m["totals"]["grand_total"], D("95"))
        self.assertEqual(m["customer"]["name"], "Buyer")
        self.assertEqual(m["items"][0]["product_code"], "P-1")
        self.assertEqual(pi.document_model(row, items), m)                # deterministic


class ErrorMapping(unittest.TestCase):
    def test_unique_indexes_of_004(self):
        for idx, reason in [("uq_pre_invoices_issued_per_request", "ACTIVE_PRE_INVOICE_EXISTS"),
                            ("uq_pre_invoices_draft_per_request", "OPEN_DRAFT_EXISTS"),
                            ("uq_pre_invoices_issued_per_chain", "ACTIVE_PRE_INVOICE_EXISTS"),
                            ("uq_pre_invoices_one_successor", "ALREADY_REPLACED")]:
            e = map_pg_error("23505", idx)
            self.assertEqual((e.code, e.details.get("reason")), (ErrorCode.DUPLICATE_RESOURCE, reason), idx)
            self.assertEqual(HTTP_STATUS[e.code], 409)

    def test_state_violations_and_internal_checks(self):
        self.assertEqual(map_pg_error("55000").code, ErrorCode.STATE_CONFLICT)
        for c in ("chk_pre_invoices_items_consistency", "chk_pre_invoices_version_chain", "chk_pre_invoices_chain_consistency"):
            self.assertEqual(map_pg_error("23514", c).code, ErrorCode.INTERNAL_ERROR, c)           # Service bug, never a client error


if __name__ == "__main__":
    unittest.main()
