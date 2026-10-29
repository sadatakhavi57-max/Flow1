import itertools
import unittest
import uuid
from decimal import Decimal as D

from tradeflow_core.authz import ACCOUNTING, ADMIN, ROLES, SALES, Cap, MATRIX, authorize
from tradeflow_core.errors import AppError
from tradeflow_core import workflow as wf
from . import pg

ME, OTHER = str(uuid.uuid4()), str(uuid.uuid4())

# The matrix of section 4, transcribed independently of authz.py (rows: capability, columns: ADMIN SALES ACCOUNTING)
EXPECTED = {
    Cap.ME_READ: (1, 1, 1), Cap.CUSTOMER_READ: (1, 1, 1), Cap.CUSTOMER_WRITE: (1, 1, 0),
    Cap.PRODUCT_READ: (1, 1, 1), Cap.PRODUCT_WRITE: (1, 0, 0), Cap.REQUEST_READ: (1, 1, 1),
    Cap.REQUEST_CREATE: (1, 1, 0), Cap.REQUEST_WRITE: (1, 1, 0), Cap.AUDIT_READ: (1, 0, 0),
}


def result(role, cap, owner=ME):
    try:
        authorize(role, cap, caller_id=ME, request_created_by=owner)
        return "OK"
    except AppError as e:
        return e.code


class Matrix(unittest.TestCase):
    def test_every_cell(self):
        self.assertEqual(set(EXPECTED), set(Cap))
        for cap, row in EXPECTED.items():
            for role, allowed in zip((ADMIN, SALES, ACCOUNTING), row):
                self.assertEqual(result(role, cap) == "OK", bool(allowed), (role, cap))

    def test_denial_codes(self):
        self.assertEqual(result(ACCOUNTING, Cap.REQUEST_WRITE), "FORBIDDEN_ROLE")
        self.assertEqual(result(SALES, Cap.AUDIT_READ), "FORBIDDEN_ROLE")
        self.assertEqual(result(SALES, Cap.PRODUCT_WRITE), "FORBIDDEN_ROLE")

    def test_sales_own_requests_only(self):
        self.assertEqual(result(SALES, Cap.REQUEST_WRITE, owner=ME), "OK")
        self.assertEqual(result(SALES, Cap.REQUEST_WRITE, owner=OTHER), "FORBIDDEN_NOT_OWNER")
        self.assertEqual(result(ADMIN, Cap.REQUEST_WRITE, owner=OTHER), "OK")                 # ADMIN: any request
        self.assertEqual(result(ACCOUNTING, Cap.REQUEST_WRITE, owner=OTHER), "FORBIDDEN_ROLE")  # role check first
        self.assertEqual(result(SALES, Cap.REQUEST_WRITE, owner=ME.upper()), "OK")            # uuid case-insensitive

    def test_reads_are_not_restricted_to_own(self):
        self.assertEqual(result(SALES, Cap.REQUEST_READ, owner=OTHER), "OK")

    def test_unknown_role_has_nothing(self):
        for cap in Cap:
            self.assertEqual(result("MANAGER", cap), "FORBIDDEN_ROLE")
            self.assertEqual(result("admin", cap), "FORBIDDEN_ROLE")                          # codes are exact

    def test_owner_check_needs_ids(self):
        with self.assertRaises(ValueError):
            authorize(SALES, Cap.REQUEST_WRITE)

    def test_admin_has_all_capabilities(self):
        self.assertEqual(MATRIX[ADMIN], frozenset(Cap))


class StateMachine(unittest.TestCase):
    def test_all_nine_pairs(self):
        allowed = {("DRAFT", "SUBMITTED"), ("DRAFT", "CANCELLED"), ("SUBMITTED", "CANCELLED")}
        for a, b in itertools.product(wf.STATUSES, repeat=2):
            try:
                wf.check_transition(a, b)
                got = True
            except AppError as e:
                self.assertEqual(e.code, "STATE_CONFLICT")
                got = False
            self.assertEqual(got, (a, b) in allowed, (a, b))

    def test_freeze_outside_draft(self):
        wf.ensure_draft("DRAFT")
        for s in ("SUBMITTED", "CANCELLED"):
            with self.assertRaises(AppError) as cm:
                wf.ensure_draft(s)
            self.assertEqual((cm.exception.code, cm.exception.http_status), ("STATE_CONFLICT", 409))

    def test_cancel_reason(self):
        self.assertEqual(wf.normalize_cancel_reason("  ok  "), "ok")
        self.assertEqual(len(wf.normalize_cancel_reason("x" * 500)), 500)
        for bad in ["", "   ", "x" * 501, None, 5]:
            with self.assertRaises(AppError) as cm:
                wf.normalize_cancel_reason(bad)
            self.assertEqual(cm.exception.code, "VALIDATION_ERROR")
        self.assertEqual(len(wf.normalize_cancel_reason(" " + "x" * 500 + " ")), 500)       # length counted after trim


def item(i="i1", price=100, pa=True, ua=True, spec=(), req=()):
    return wf.ItemForSubmit(i, D(price), pa, ua, list(spec), list(req))


def submit_code(status="DRAFT", cust=True, items=None):
    try:
        wf.check_submit(status, cust, items if items is not None else [item()])
        return "OK", None
    except AppError as e:
        return e.code, e.details


class Submit(unittest.TestCase):
    def test_happy_path(self):
        self.assertEqual(submit_code()[0], "OK")

    def test_order_of_checks(self):
        self.assertEqual(submit_code("SUBMITTED")[0], "STATE_CONFLICT")                     # repeat submit is 409, not success
        self.assertEqual(submit_code("CANCELLED")[0], "STATE_CONFLICT")
        # status wins over everything else
        self.assertEqual(submit_code("SUBMITTED", cust=False, items=[])[0], "STATE_CONFLICT")
        # inactive reference wins over NO_ITEMS / price / spec problems
        self.assertEqual(submit_code(cust=False, items=[])[0], "INACTIVE_REFERENCE")
        self.assertEqual(submit_code(items=[item(pa=False, price=0)])[0], "INACTIVE_REFERENCE")
        self.assertEqual(submit_code(items=[item(ua=False)])[0], "INACTIVE_REFERENCE")
        self.assertEqual(submit_code(items=[])[1], {"reason": "NO_ITEMS"})
        c, d = submit_code(items=[item("a", 100), item("b", 0)])
        self.assertEqual((c, d), ("SUBMIT_PRECONDITION_FAILED", {"reason": "ITEM_PRICE_MISSING", "item_id": "b"}))
        # price problem is reported before a missing specification
        c, d = submit_code(items=[item("a", 0, req=["f1"]), item("b", 100)])
        self.assertEqual(d["reason"], "ITEM_PRICE_MISSING")

    def test_required_specification(self):
        c, d = submit_code(items=[item("a", req=["F1"])])
        self.assertEqual(d, {"reason": "REQUIRED_SPECIFICATION_MISSING", "item_id": "a", "field_id": "F1"})
        ok = item("a", req=["F1"], spec=[{"field_id": "f1"}])                               # case-insensitive ids
        self.assertEqual(submit_code(items=[ok])[0], "OK")

    def test_422_for_preconditions(self):
        self.assertEqual(AppError("SUBMIT_PRECONDITION_FAILED").http_status, 422)


@unittest.skipUnless(pg.available(), "PostgreSQL (psql) not available")
class TransitionsAgainstDatabase(unittest.TestCase):
    """The Python transition table must equal what the real trigger of migration 002 allows (55000 otherwise)."""

    @classmethod
    def setUpClass(cls):
        cls.db = pg.make_db("tf_core_state")
        org = pg.psql(cls.db, "select id from organizations where code='DEMO'")
        cust = pg.psql(cls.db, "select id from customers limit 1")
        uid = pg.psql(cls.db, "select id from users where username='admin'")
        cls.ins = lambda self, n, status="DRAFT": pg.psql(
            cls.db, f"insert into purchase_requests(organization_id,request_number,customer_id,created_by,status) "
                    f"values ('{org}','T-{n}','{cust}','{uid}','DRAFT') returning id")

    def test_python_table_equals_database(self):
        n = 0
        for a, b in itertools.product(wf.STATUSES, repeat=2):
            n += 1
            rid = self.ins(n).splitlines()[0]
            # bring the row to state `a` through legal steps
            path = {"DRAFT": [], "SUBMITTED": ["SUBMITTED"], "CANCELLED": ["CANCELLED"]}[a]
            for s in path:
                pg.psql(self.db, f"update purchase_requests set status='{s}' where id='{rid}'")
            try:
                pg.psql(self.db, f"update purchase_requests set status='{b}' where id='{rid}'")
                db_ok = True
            except pg.PgError as e:
                self.assertEqual(e.sqlstate, "55000", (a, b, e))
                db_ok = False
            try:
                wf.check_transition(a, b)
                py_ok = True
            except AppError:
                py_ok = False
            if a == b:                       # same-status UPDATE is not a transition; the API never issues it
                continue
            self.assertEqual(py_ok, db_ok, (a, b))
