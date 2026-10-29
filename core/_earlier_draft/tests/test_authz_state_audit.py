import itertools, unittest
from decimal import Decimal as D

from tradeflow_core import audit, authz, state
from tradeflow_core.authz import Cap, authorize
from tradeflow_core.concurrency import check_updated_at, parse_updated_at
from tradeflow_core.errors import DomainError, HTTP_STATUS, map_pg_error
from datetime import datetime, timezone

# The matrix of contract section 4, written out independently of authz.MATRIX (rows = capability).
EXPECT = {  #                 ADMIN SALES ACCOUNTING
    Cap.ME:              (1, 1, 1), Cap.ORG_READ: (1, 1, 1), Cap.LOOKUP_READ: (1, 1, 1),
    Cap.CUSTOMER_READ:   (1, 1, 1), Cap.CUSTOMER_WRITE: (1, 1, 0),
    Cap.PRODUCT_READ:    (1, 1, 1), Cap.PRODUCT_WRITE: (1, 0, 0),
    Cap.REQUEST_READ:    (1, 1, 1), Cap.REQUEST_CREATE: (1, 1, 0), Cap.REQUEST_WRITE: (1, 1, 0),
    Cap.AUDIT_READ:      (1, 0, 0),
}


def code_of(fn):
    try:
        fn()
    except DomainError as e:
        return e.code
    return None


class Authz(unittest.TestCase):
    def test_full_matrix(self):
        self.assertEqual(set(EXPECT), set(Cap))
        for cap, row in EXPECT.items():
            for role, allowed in zip(("ADMIN", "SALES", "ACCOUNTING"), row):
                got = code_of(lambda: authorize(role, cap, caller_id="u1", request_owner_id="u1"))
                self.assertEqual(got, None if allowed else "FORBIDDEN_ROLE", (cap, role))

    def test_ownership(self):
        self.assertIsNone(code_of(lambda: authorize("SALES", Cap.REQUEST_WRITE, caller_id="u1", request_owner_id="u1")))
        self.assertEqual(code_of(lambda: authorize("SALES", Cap.REQUEST_WRITE, caller_id="u1", request_owner_id="u2")), "FORBIDDEN_NOT_OWNER")
        self.assertEqual(code_of(lambda: authorize("SALES", Cap.REQUEST_WRITE)), "FORBIDDEN_NOT_OWNER")     # fail closed
        self.assertIsNone(code_of(lambda: authorize("ADMIN", Cap.REQUEST_WRITE, caller_id="a", request_owner_id="s")))
        self.assertEqual(code_of(lambda: authorize("ACCOUNTING", Cap.REQUEST_WRITE, caller_id="x", request_owner_id="x")), "FORBIDDEN_ROLE")

    def test_unknown_role_and_none_are_denied(self):
        for r in (None, "", "admin", "ROOT"):
            for cap in Cap:
                self.assertEqual(code_of(lambda: authorize(r, cap)), "FORBIDDEN_ROLE", (r, cap))

    def test_http_status(self):
        self.assertEqual(HTTP_STATUS["FORBIDDEN_ROLE"], 403)


class StateMachine(unittest.TestCase):
    def test_all_nine_pairs(self):
        legal = {("DRAFT", "SUBMITTED"), ("DRAFT", "CANCELLED"), ("SUBMITTED", "CANCELLED")}
        for a, b in itertools.product(state.STATUSES, repeat=2):
            self.assertEqual(code_of(lambda: state.ensure_transition(a, b)), None if (a, b) in legal else "STATE_CONFLICT", (a, b))

    def test_freeze(self):
        self.assertIsNone(code_of(lambda: state.ensure_content_editable("DRAFT")))
        for s in ("SUBMITTED", "CANCELLED"):
            self.assertEqual(code_of(lambda: state.ensure_content_editable(s)), "STATE_CONFLICT")

    def test_cancel_reason(self):
        self.assertEqual(state.cancel_reason("  customer withdrew  "), "customer withdrew")
        self.assertEqual(len(state.cancel_reason("x" * 500)), 500)
        for bad in ("", "   ", "x" * 501, None, 5, "​"[:0]):
            self.assertEqual(code_of(lambda: state.cancel_reason(bad)), "VALIDATION_ERROR", repr(bad))
        self.assertEqual(code_of(lambda: state.cancel_reason(" " + "x" * 501 + " ")), "VALIDATION_ERROR")
        self.assertIsNone(code_of(lambda: state.cancel_reason(" " + "x" * 500 + " ")))       # length counted after trim


def item(id_="i1", price="100", pa=True, ua=True, snap=(), req=()):
    return {"id": id_, "unit_price": D(price), "product_active": pa, "unit_active": ua, "snapshot": list(snap), "required_field_ids": list(req)}


class Submit(unittest.TestCase):
    def check(self, status="DRAFT", cust=True, items=None):
        try:
            state.check_submit(status, cust, [item()] if items is None else items)
        except DomainError as e:
            return e.code, (e.details.get("reason") if isinstance(e.details, dict) else None), e.details
        return None

    def test_ok(self):
        self.assertIsNone(self.check())

    def test_order_of_checks(self):
        self.assertEqual(self.check(status="SUBMITTED", cust=False, items=[])[0], "STATE_CONFLICT")       # status first
        self.assertEqual(self.check(cust=False, items=[])[0], "INACTIVE_REFERENCE")                      # then references
        self.assertEqual(self.check(items=[])[:2], ("SUBMIT_PRECONDITION_FAILED", "NO_ITEMS"))
        self.assertEqual(self.check(items=[item(price="0")])[:2], ("SUBMIT_PRECONDITION_FAILED", "ITEM_PRICE_MISSING"))
        self.assertEqual(self.check(items=[item(pa=False)])[0], "INACTIVE_REFERENCE")
        self.assertEqual(self.check(items=[item(ua=False)])[0], "INACTIVE_REFERENCE")

    def test_required_specifications(self):
        r = self.check(items=[item("i9", req=["f1", "f2"], snap=[{"field_id": "f1"}])])
        self.assertEqual(r[:2], ("SUBMIT_PRECONDITION_FAILED", "REQUIRED_SPECIFICATION_MISSING"))
        self.assertEqual((r[2]["item_id"], r[2]["field_id"]), ("i9", "f2"))
        self.assertIsNone(self.check(items=[item(req=["f1"], snap=[{"field_id": "f1"}])]))

    def test_price_check_is_strictly_positive(self):
        self.assertIsNone(self.check(items=[item(price="1")]))


class Concurrency(unittest.TestCase):
    T = datetime(2026, 10, 8, 9, 20, 11, 123456, tzinfo=timezone.utc)

    def test_exact_match(self):
        check_updated_at("2026-10-08T09:20:11.123456Z", self.T)

    def test_microsecond_difference_is_stale(self):
        with self.assertRaises(DomainError) as c:
            check_updated_at("2026-10-08T09:20:11.123457Z", self.T, {"id": "x"})
        self.assertEqual((c.exception.code, c.exception.details["current"]), ("STALE_UPDATE", {"id": "x"}))

    def test_short_fraction_is_padded(self):
        check_updated_at("2026-10-08T09:20:11.5Z", self.T.replace(microsecond=500000))

    def test_missing_or_bad_format(self):
        for bad in (None, 5, "", "2026-10-08", "2026-10-08T09:20:11+00:00", "2026-13-08T09:20:11Z"):
            self.assertEqual(code_of(lambda: parse_updated_at(bad)), "VALIDATION_ERROR", repr(bad))


class Audit(unittest.TestCase):
    def test_closed_vocabulary(self):
        self.assertEqual({a.value for a in audit.Action}, {"CREATE", "UPDATE", "DELETE", "SUBMIT", "CANCEL", "LOGIN", "LOGOUT"})
        self.assertEqual({e.value for e in audit.Entity}, {"USER", "CUSTOMER", "PRODUCT", "PURCHASE_REQUEST", "PURCHASE_REQUEST_ITEM"})
        for bad_action in ("APPROVE", "create", "", "LOGIN_FAILED"):
            with self.assertRaises(ValueError):
                audit.make_record(organization_id="o", user_id="u", action=bad_action, entity_type="USER")
        with self.assertRaises(ValueError):
            audit.make_record(organization_id="o", user_id="u", action="CREATE", entity_type="INVOICE")
        with self.assertRaises(ValueError):
            audit.make_record(organization_id=None, user_id="u", action="CREATE", entity_type="USER")

    def test_secrets_never_stored(self):
        r = audit.make_record(organization_id="o", user_id="u", action="CREATE", entity_type="USER", entity_id="e",
                              new_data={"username": "a", "password_hash": "x", "nested": {"Refresh_Token": "t", "ok": 1},
                                        "list": [{"token_hash": "h", "k": 2}]})
        self.assertEqual(r.new_data, {"username": "a", "nested": {"ok": 1}, "list": [{"k": 2}]})

    def test_changed_fields(self):
        o, n = audit.changed_fields({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 5, "c": 3, "d": 9})
        self.assertEqual((o, n), ({"b": 2, "d": None}, {"b": 5, "d": 9}))


class PgErrorMapping(unittest.TestCase):
    def test_mapping(self):
        m = map_pg_error
        self.assertEqual(m("55000").code, "STATE_CONFLICT")
        self.assertEqual((m("23505", "uq_customers_org_national_id").code, m("23505", "uq_customers_org_national_id").details), ("DUPLICATE_IDENTIFIER", {"field": "national_id"}))
        self.assertEqual(m("23505", "uq_customers_org_economic_code").details, {"field": "economic_code"})
        self.assertEqual((m("23505", "uq_products_org_name").code, m("23505", "uq_products_org_name").details), ("DUPLICATE_RESOURCE", {"field": "name"}))
        self.assertEqual(m("23505", "uq_products_org_code").details, {"field": "code"})
        self.assertEqual(m("23505", "uq_organizations_code").code, "DUPLICATE_RESOURCE")
        self.assertEqual(m("23503").code, "REFERENCE_NOT_FOUND")
        self.assertEqual(m("22003").code, "AMOUNT_OUT_OF_RANGE")
        self.assertEqual(m("23514", "chk_request_items_line_total_consistency").code, "AMOUNT_OUT_OF_RANGE")
        self.assertEqual(m("23514", "chk_purchase_requests_delivery_date").code, "VALIDATION_ERROR")
        self.assertEqual(m("40P01").code, "TEMPORARILY_UNAVAILABLE")
        self.assertEqual(m("08006").code, "TEMPORARILY_UNAVAILABLE")
        self.assertEqual(m("XX000").code, "INTERNAL_ERROR")
        self.assertEqual(m("42601", None, "syntax error near SELECT secret").message, "Unexpected error.")       # no SQL echoed

    def test_body_envelope_always_has_details(self):
        b = map_pg_error("XX000").body("rid")
        self.assertEqual(set(b["error"]), {"code", "message", "details", "request_id"})
        self.assertEqual(b["error"]["details"], {})


if __name__ == "__main__":
    unittest.main()
