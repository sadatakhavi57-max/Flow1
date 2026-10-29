import itertools
import re
import unittest
from datetime import datetime, timezone
from decimal import Decimal as D

from tradeflow_core import authz, state, audit, concurrency as cc
from tradeflow_core.errors import AppError, ErrorCode, HTTP_STATUS
from . import contract_doc as doc

CONTRACT = doc.contract_path()
TEXT = CONTRACT.read_text(encoding="utf-8") if CONTRACT else ""


def code_of(fn, *a, **k):
    try:
        fn(*a, **k)
    except AppError as e:
        return e.code
    return None


class Authz(unittest.TestCase):
    # Written out independently of authz.MATRIX: section 4 of the contract, row by row. (A, S, C) = ADMIN, SALES, ACCOUNTING
    EXPECT = {
        authz.Cap.ME: "ASC", authz.Cap.ORG_READ: "ASC", authz.Cap.LOOKUP_READ: "ASC",
        authz.Cap.CUSTOMER_READ: "ASC", authz.Cap.CUSTOMER_WRITE: "AS-",
        authz.Cap.PRODUCT_READ: "ASC", authz.Cap.PRODUCT_WRITE: "A--",
        authz.Cap.REQUEST_READ: "ASC", authz.Cap.REQUEST_CREATE: "AS-", authz.Cap.REQUEST_WRITE: "AS-",
        authz.Cap.AUDIT_READ: "A--",
        # Stage 4 (contract section 4, pre-invoice rows)
        authz.Cap.PREINVOICE_READ: "ASC", authz.Cap.PREINVOICE_CREATE: "AS-", authz.Cap.PREINVOICE_ISSUE: "A-C",
        authz.Cap.PREINVOICE_CANCEL_DRAFT: "AS-", authz.Cap.PREINVOICE_CANCEL_ISSUED: "A-C", authz.Cap.PREINVOICE_PDF: "A-C",
    }

    def test_full_matrix_table_driven(self):
        roles = {"A": "ADMIN", "S": "SALES", "C": "ACCOUNTING"}
        for cap, flags in self.EXPECT.items():
            for letter, role in roles.items():
                allowed = letter in flags
                kwargs = dict(caller_id="u1", owner_id="u1")           # own request: ownership is not the question here
                got = code_of(authz.authorize, role, cap, **kwargs)
                self.assertEqual(got is None, allowed, (cap, role, got))
                if not allowed:
                    self.assertEqual(got, ErrorCode.FORBIDDEN_ROLE)

    def test_every_capability_is_covered(self):
        self.assertEqual(set(self.EXPECT), set(authz.Cap))

    def test_sales_own_requests_only(self):
        w = authz.Cap.REQUEST_WRITE
        self.assertIsNone(code_of(authz.authorize, "SALES", w, caller_id="U1", owner_id="u1"))        # case-insensitive ids
        self.assertEqual(code_of(authz.authorize, "SALES", w, caller_id="u1", owner_id="u2"), ErrorCode.FORBIDDEN_NOT_OWNER)
        self.assertEqual(code_of(authz.authorize, "SALES", w, caller_id="u1", owner_id=None), ErrorCode.FORBIDDEN_NOT_OWNER)
        self.assertEqual(code_of(authz.authorize, "SALES", w), ErrorCode.FORBIDDEN_NOT_OWNER)
        self.assertIsNone(code_of(authz.authorize, "ADMIN", w, caller_id="u1", owner_id="u2"))        # ADMIN: any request
        self.assertEqual(code_of(authz.authorize, "ACCOUNTING", w, caller_id="u1", owner_id="u1"), ErrorCode.FORBIDDEN_ROLE)

    def test_sales_own_pre_invoices_only(self):
        for cap in (authz.Cap.PREINVOICE_READ, authz.Cap.PREINVOICE_CREATE, authz.Cap.PREINVOICE_CANCEL_DRAFT):
            self.assertIsNone(code_of(authz.authorize, "SALES", cap, caller_id="U1", owner_id="u1"), cap)
            self.assertEqual(code_of(authz.authorize, "SALES", cap, caller_id="u1", owner_id="u2"), ErrorCode.FORBIDDEN_NOT_OWNER, cap)
            self.assertEqual(code_of(authz.authorize, "SALES", cap, caller_id="u1", owner_id=None), ErrorCode.FORBIDDEN_NOT_OWNER, cap)
            self.assertTrue(authz.is_own_only("SALES", cap))
            self.assertFalse(authz.is_own_only("ADMIN", cap))
            self.assertFalse(authz.is_own_only("ACCOUNTING", cap))
        # ACCOUNTING sees every pre-invoice (no ownership limit) but cannot create or cancel a DRAFT
        self.assertIsNone(code_of(authz.authorize, "ACCOUNTING", authz.Cap.PREINVOICE_READ, caller_id="u1", owner_id="u2"))
        self.assertEqual(code_of(authz.authorize, "ACCOUNTING", authz.Cap.PREINVOICE_CREATE, caller_id="u1", owner_id="u1"), ErrorCode.FORBIDDEN_ROLE)
        self.assertTrue(authz.is_own_only("SUPERUSER", authz.Cap.PREINVOICE_READ))              # unknown role: most restrictive reading
        self.assertFalse(authz.has_capability("SUPERUSER", authz.Cap.PREINVOICE_READ))
        self.assertTrue(authz.has_capability("ACCOUNTING", authz.Cap.PREINVOICE_ISSUE))

    def test_audit_read_is_not_widened(self):
        self.assertEqual(authz.MATRIX[authz.Cap.AUDIT_READ], frozenset({authz.Role.ADMIN}))
        self.assertNotIn(authz.Role.ACCOUNTING, authz.MATRIX[authz.Cap.REQUEST_WRITE])          # ACCOUNTING still has no REQUEST_WRITE

    def test_unknown_roles_are_denied_everything(self):
        for role in ["SUPERUSER", "admin", "", "ADMIN ", None, "Sales"]:
            for cap in authz.Cap:
                self.assertEqual(code_of(authz.authorize, role, cap), ErrorCode.FORBIDDEN_ROLE, (role, cap))

    @unittest.skipUnless(CONTRACT, "SKIPPED: contract file not found (set TF_CONTRACT)")
    def test_matrix_equals_the_contract_table(self):
        rows = doc.table_rows(doc.section(TEXT, "4. Authorization"))
        mapping = {"`me`, organizations (read)": [authz.Cap.ME, authz.Cap.ORG_READ],
                   "customers: read": [authz.Cap.CUSTOMER_READ], "customers: create / patch": [authz.Cap.CUSTOMER_WRITE],
                   "products + specifications: read": [authz.Cap.PRODUCT_READ], "products: create / patch": [authz.Cap.PRODUCT_WRITE],
                   "purchase requests, pricing: read": [authz.Cap.REQUEST_READ], "purchase requests: create": [authz.Cap.REQUEST_CREATE],
                   "request / items / pricing: write, submit, cancel": [authz.Cap.REQUEST_WRITE], "audit-logs: read": [authz.Cap.AUDIT_READ],
                   "pre-invoices: read (list, get, PDF download)": [authz.Cap.PREINVOICE_READ],
                   "pre-invoices: create a DRAFT": [authz.Cap.PREINVOICE_CREATE], "pre-invoices: issue": [authz.Cap.PREINVOICE_ISSUE],
                   "pre-invoices: cancel a DRAFT": [authz.Cap.PREINVOICE_CANCEL_DRAFT],
                   "pre-invoices: cancel an ISSUED document": [authz.Cap.PREINVOICE_CANCEL_ISSUED],
                   "pre-invoices: generate / retry the PDF": [authz.Cap.PREINVOICE_PDF]}
        seen = set()
        for r in rows:
            caps = mapping[r[0]]
            for cap in caps:
                seen.add(cap)
                for col, role in zip(r[1:4], [authz.Role.ADMIN, authz.Role.SALES, authz.Role.ACCOUNTING]):
                    self.assertEqual(role in authz.MATRIX[cap], col.strip("* ") != "–", (r[0], role, col))
        self.assertEqual(seen | {authz.Cap.LOOKUP_READ}, set(authz.Cap))          # lookups: "All three roles may read them" (section 7)


class StateMachine(unittest.TestCase):
    def test_all_nine_transitions(self):
        allowed = {("DRAFT", "SUBMITTED"), ("DRAFT", "CANCELLED"), ("SUBMITTED", "CANCELLED")}
        for a, b in itertools.product(["DRAFT", "SUBMITTED", "CANCELLED"], repeat=2):
            got = code_of(state.assert_transition, a, b)
            self.assertEqual(got is None, (a, b) in allowed, (a, b))
            if (a, b) not in allowed:
                self.assertEqual(got, ErrorCode.STATE_CONFLICT)
        self.assertEqual(code_of(state.assert_transition, "DRAFT", "DONE"), ErrorCode.STATE_CONFLICT)

    def test_freeze(self):
        self.assertIsNone(code_of(state.assert_editable, "DRAFT"))
        for s in ["SUBMITTED", "CANCELLED", "whatever"]:
            self.assertEqual(code_of(state.assert_editable, s), ErrorCode.STATE_CONFLICT)

    def test_cancel_reason(self):
        self.assertEqual(state.validate_cancel_reason("  customer withdrew "), "customer withdrew")
        self.assertEqual(state.validate_cancel_reason("x" * 500), "x" * 500)
        for bad in ["", "   ", "x" * 501, None, 5, ["a"]]:
            self.assertEqual(code_of(state.validate_cancel_reason, bad), ErrorCode.VALIDATION_ERROR, repr(bad))
        self.assertEqual(len(state.validate_cancel_reason(" " * 10 + "x" * 500 + " " * 10)), 500)   # length counted after trim

    def test_product_immutable(self):
        self.assertIsNone(code_of(state.assert_product_unchanged, "P1", {"quantity": "1"}))
        self.assertIsNone(code_of(state.assert_product_unchanged, "P1", {"product_id": "p1"}))
        self.assertEqual(code_of(state.assert_product_unchanged, "P1", {"product_id": "P2"}), ErrorCode.VALIDATION_ERROR)

    def item(self, **kw):
        base = dict(id="i1", product_active=True, unit_active=True, unit_price=D(10), snapshot=[], required_field_ids=())
        base.update(kw)
        return state.SubmitItem(**base)

    def test_submit_order_and_details(self):
        ok = [self.item()]
        self.assertIsNone(code_of(state.check_submit, "DRAFT", True, ok))
        for s in ["SUBMITTED", "CANCELLED"]:
            self.assertEqual(code_of(state.check_submit, s, True, ok), ErrorCode.STATE_CONFLICT)       # repeat submit is 409
        self.assertEqual(code_of(state.check_submit, "DRAFT", False, ok), ErrorCode.INACTIVE_REFERENCE)
        self.assertEqual(code_of(state.check_submit, "DRAFT", True, [self.item(unit_active=False)]), ErrorCode.INACTIVE_REFERENCE)
        self.assertEqual(code_of(state.check_submit, "DRAFT", True, [self.item(product_active=False)]), ErrorCode.INACTIVE_REFERENCE)

        def details(items, cust=True):
            try:
                state.check_submit("DRAFT", cust, items)
            except AppError as e:
                return e.code, e.details
        self.assertEqual(details([]), (ErrorCode.SUBMIT_PRECONDITION_FAILED, {"reason": "NO_ITEMS"}))
        self.assertEqual(details([self.item(), self.item(id="i2", unit_price=D(0))]),
                         (ErrorCode.SUBMIT_PRECONDITION_FAILED, {"reason": "ITEM_PRICE_MISSING", "item_id": "i2"}))
        miss = self.item(id="i3", required_field_ids=("F1", "F0"), snapshot=[{"field_id": "f0"}])
        self.assertEqual(details([miss]), (ErrorCode.SUBMIT_PRECONDITION_FAILED,
                                           {"reason": "REQUIRED_SPECIFICATION_MISSING", "item_id": "i3", "field_id": "f1"}))
        # precedence: inactive reference beats no price; no items beats nothing else
        self.assertEqual(details([self.item(unit_price=D(0), unit_active=False)])[0], ErrorCode.INACTIVE_REFERENCE)
        self.assertEqual(details([self.item(unit_price=D(0), required_field_ids=("F1",))])[1]["reason"], "ITEM_PRICE_MISSING")


class Concurrency(unittest.TestCase):
    T = datetime(2026, 10, 8, 9, 20, 11, 123456, tzinfo=timezone.utc)

    def test_format_roundtrip(self):
        s = cc.format_ts(self.T)
        self.assertEqual(s, "2026-10-08T09:20:11.123456Z")
        self.assertEqual(cc.parse_ts(s), self.T)
        self.assertEqual(cc.format_ts(self.T.replace(microsecond=0)), "2026-10-08T09:20:11.000000Z")     # always six digits

    def test_exact_match_only(self):
        self.assertIsNone(code_of(cc.check_not_stale, "2026-10-08T09:20:11.123456Z", self.T))
        self.assertEqual(code_of(cc.check_not_stale, "2026-10-08T09:20:11.123457Z", self.T), ErrorCode.STALE_UPDATE)   # 1 microsecond
        self.assertEqual(code_of(cc.check_not_stale, None, self.T), ErrorCode.VALIDATION_ERROR)
        for bad in ["2026-10-08T09:20:11Z", "2026-10-08 09:20:11.123456", "2026-10-08T09:20:11.123Z", "x", 5, "2026-13-08T09:20:11.123456Z"]:
            self.assertEqual(code_of(cc.check_not_stale, bad, self.T), ErrorCode.VALIDATION_ERROR, repr(bad))

    def test_stale_carries_current_resource(self):
        try:
            cc.check_not_stale("2020-01-01T00:00:00.000000Z", self.T, {"id": "x"})
        except AppError as e:
            self.assertEqual(e.details, {"current": {"id": "x"}})


class Audit(unittest.TestCase):
    def test_closed_sets(self):
        self.assertEqual({a.value for a in audit.AuditAction}, {"CREATE", "UPDATE", "DELETE", "SUBMIT", "CANCEL", "LOGIN", "LOGOUT",
                                                                          "ISSUE", "SUPERSEDE", "PDF_GENERATE", "PDF_FAIL"})
        self.assertEqual({a.value for a in audit.AuditEntity}, {"USER", "CUSTOMER", "PRODUCT", "PURCHASE_REQUEST", "PURCHASE_REQUEST_ITEM",
                                                                        "PRE_INVOICE"})
        kw = dict(organization_id="o", user_id="u", entity_id="e")
        self.assertEqual(audit.build_entry("SUBMIT", "PURCHASE_REQUEST", **kw)["action"], "SUBMIT")
        for a, e in [("APPROVE", "USER"), ("create", "USER"), ("CREATE", "ORDER"), ("LOGIN_FAILED", "USER"), ("", "USER")]:
            with self.assertRaises(ValueError): audit.build_entry(a, e, **kw)

    def test_secrets_never_reach_audit(self):
        kw = dict(organization_id="o", user_id="u", entity_id="e")
        for bad in [{"password_hash": "x"}, {"a": {"b": [{"Refresh_Token": "x"}]}}, {"token": 1}, {"password": "p"}]:
            with self.assertRaises(ValueError): audit.build_entry("UPDATE", "USER", new_data=bad, **kw)
            with self.assertRaises(ValueError): audit.build_entry("UPDATE", "USER", old_data=bad, **kw)
        audit.build_entry("UPDATE", "USER", new_data={"first_name": "A", "role": {"code": "ADMIN"}}, **kw)

    def test_organization_mandatory(self):
        with self.assertRaises(ValueError): audit.build_entry("LOGIN", "USER", organization_id="", user_id="u", entity_id="u")

    @unittest.skipUnless(CONTRACT, "SKIPPED: contract file not found")
    def test_vocabulary_equals_contract_section_13(self):
        sec = doc.section(TEXT, "13. Audit contract")
        acts = re.search(r"\*\*Actions \(closed set\)\*\* \[D4\]: (.*?)\. `LOGOUT`", sec, re.S).group(1)
        self.assertEqual(set(re.findall(r"`([A-Z_]+)`", acts)), {a.value for a in audit.AuditAction})
        ents = re.search(r"\*\*Entity types \(closed set\):\*\* (.*?)\. Both are", sec, re.S).group(1)
        self.assertEqual(set(re.findall(r"`([A-Z_]+)`", ents)), {a.value for a in audit.AuditEntity})


class ErrorTable(unittest.TestCase):
    @unittest.skipUnless(CONTRACT, "SKIPPED: contract file not found")
    def test_error_codes_and_statuses_equal_contract_section_15(self):
        rows = doc.table_rows(doc.section(TEXT, "15. Error codes"))
        doc_map = {re.sub(r"[` ]|\(.*\)", "", r[1]): int(r[0]) for r in rows}
        self.assertEqual(doc_map, {c.value: s for c, s in HTTP_STATUS.items()})

    def test_body_shape(self):
        b = AppError(ErrorCode.NOT_FOUND, details={"resource": "customer"}).to_body("rid-1")
        self.assertEqual(b, {"error": {"code": "NOT_FOUND", "message": "Not found", "details": {"resource": "customer"}, "request_id": "rid-1"}})
        self.assertEqual(AppError(ErrorCode.INTERNAL_ERROR).details, {})                    # details always present


if __name__ == "__main__":
    unittest.main()
