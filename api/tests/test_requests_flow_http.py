"""Purchase requests part 2: T-STATE, T-ROLE/ownership, T-TENANT, T-RACE, T-AUDIT, audit-logs, T-E2E."""
import threading
import unittest
import uuid

from fastapi.testclient import TestClient

from tests import pg, support
from tests.test_requests_http import R, RI, RequestsBase, err

API = "/api/v1"


class RequestsFlow(RequestsBase):
    def ready_request(self, headers=None):
        """A DRAFT with one priced item that carries the required specification."""
        return self.mk(headers=headers, items=[self.item()])

    # ------------------------------------------------------------------ submit
    def test_submit_preconditions_in_contract_order(self):
        d = self.mk()
        r = self.c.post(f"{R}/{d['id']}/submit", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]), (422, "SUBMIT_PRECONDITION_FAILED", {"reason": "NO_ITEMS"}))
        free = self.add(d["id"], unit_price="0")["item"]
        r = self.c.post(f"{R}/{d['id']}/submit", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["details"]), (422, {"reason": "ITEM_PRICE_MISSING", "item_id": free["id"]}))
        r = self.c.patch(f"{RI}/{free['id']}", json={"unit_price": "10", "specifications": [], "updated_at": free["updated_at"]}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        r = self.c.post(f"{R}/{d['id']}/submit", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["details"]), (422, {"reason": "REQUIRED_SPECIFICATION_MISSING", "item_id": free["id"], "field_id": self.f_diam}))
        cur = self.c.get(f"{R}/{d['id']}", headers=self.admin).json()["data"]["items"][0]
        self.assertEqual(self.c.patch(f"{RI}/{free['id']}", json={"specifications": self.spec, "updated_at": cur["updated_at"]}, headers=self.admin).status_code, 200)
        r = self.c.post(f"{R}/{d['id']}/submit", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["data"]["status"], r.json()["data"]["grand_total"], len(r.json()["data"]["items"])), ("SUBMITTED", "100", 1))

    def test_submit_rechecks_active_references(self):
        prod = self.new_product()
        d = self.mk(items=[self.item(product_id=prod["id"])])
        pr = self.c.patch(f"/api/v1/products/{prod['id']}", json={"is_active": False, "updated_at": prod["updated_at"]}, headers=self.admin)
        self.assertEqual(pr.status_code, 200)
        r = self.c.post(f"{R}/{d['id']}/submit", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "INACTIVE_REFERENCE"))
        self.assertEqual(err(r)["details"], [{"resource": "product", "item_id": d["items"][0]["id"]}])
        self.assertEqual(self.get(d["id"])["status"], "DRAFT")
        c2 = self.c.post("/api/v1/customers", json={"customer_type": "COMPANY", "name": "tmp-" + uuid.uuid4().hex[:8]}, headers=self.admin).json()["data"]
        d2 = self.mk(customer_id=c2["id"], items=[self.item()])
        self.c.patch(f"/api/v1/customers/{c2['id']}", json={"is_active": False, "updated_at": c2["updated_at"]}, headers=self.admin)
        r = self.c.post(f"{R}/{d2['id']}/submit", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]), (422, "INACTIVE_REFERENCE", [{"resource": "customer"}]))

    # ------------------------------------------------------------------ T-STATE
    def test_state_machine_and_freeze(self):
        d = self.ready_request()
        item = d["items"][0]
        sub = self.c.post(f"{R}/{d['id']}/submit", headers=self.admin)
        self.assertEqual(sub.status_code, 200, sub.text)
        frozen = sub.json()["data"]
        self.assertEqual(frozen["updated_by"], d["created_by"])
        for call in (lambda: self.c.post(f"{R}/{d['id']}/submit", headers=self.admin),
                     lambda: self.c.patch(f"{R}/{d['id']}", json={"notes": "n", "updated_at": frozen["updated_at"]}, headers=self.admin),
                     lambda: self.c.post(f"{R}/{d['id']}/items", json=self.item(), headers=self.admin),
                     lambda: self.c.patch(f"{RI}/{item['id']}", json={"quantity": "2", "updated_at": item["updated_at"]}, headers=self.admin),
                     lambda: self.c.delete(f"{RI}/{item['id']}", headers=self.admin),
                     lambda: self.c.post(f"{R}/{d['id']}/pricing", json={"updated_at": frozen["updated_at"], "lines": [{"item_id": item["id"], "unit_price": "5"}]}, headers=self.admin)):
            r = call()
            self.assertEqual((r.status_code, err(r)["code"]), (409, "STATE_CONFLICT"))
        after = self.get(d["id"])
        self.assertEqual((after, ), (frozen, ))                                                                # nothing changed at all
        c = self.c.post(f"{R}/{d['id']}/cancel", json={"reason": "  customer withdrew  "}, headers=self.admin)  # SUBMITTED -> CANCELLED
        self.assertEqual((c.status_code, c.json()["data"]["status"]), (200, "CANCELLED"))
        for call in (lambda: self.c.post(f"{R}/{d['id']}/cancel", json={"reason": "again"}, headers=self.admin),
                     lambda: self.c.post(f"{R}/{d['id']}/submit", headers=self.admin),
                     lambda: self.c.patch(f"{R}/{d['id']}", json={"notes": "n", "updated_at": c.json()["data"]["updated_at"]}, headers=self.admin),
                     lambda: self.c.post(f"{R}/{d['id']}/items", json=self.item(), headers=self.admin)):
            r = call()
            self.assertEqual((r.status_code, err(r)["code"]), (409, "STATE_CONFLICT"))
        self.assertEqual(self.get(d["id"])["items"][0]["id"], item["id"])                                      # a cancelled request keeps its data

    def test_cancel_from_draft_and_reason_rules(self):
        d = self.mk()
        for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}, {"reason": 5}, {"reason": "ok", "status": "X"}):
            r = self.c.post(f"{R}/{d['id']}/cancel", json=body, headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"), body)
        self.assertEqual(self.get(d["id"])["status"], "DRAFT")
        r = self.c.post(f"{R}/{d['id']}/cancel", json={"reason": "x" * 500}, headers=self.admin)
        self.assertEqual((r.status_code, r.json()["data"]["status"]), (200, "CANCELLED"))

    # ------------------------------------------------------------------ T-ROLE and ownership
    def test_role_matrix_and_ownership(self):
        mine = self.mk(headers=self.sales, items=[self.item()])
        self.assertEqual(mine["created_by"], support.scalar("SELECT id FROM users WHERE username = 'sales'"))
        r = self.c.post(R, json={"customer_id": self.cust}, headers=self.acct)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
        item = mine["items"][0]
        writes = [lambda h: self.c.patch(f"{R}/{mine['id']}", json={"notes": "x", "updated_at": mine["updated_at"]}, headers=h),
                  lambda h: self.c.post(f"{R}/{mine['id']}/items", json=self.item(), headers=h),
                  lambda h: self.c.patch(f"{RI}/{item['id']}", json={"quantity": "3", "updated_at": item["updated_at"]}, headers=h),
                  lambda h: self.c.delete(f"{RI}/{item['id']}", headers=h),
                  lambda h: self.c.post(f"{R}/{mine['id']}/pricing", json={"updated_at": mine["updated_at"], "lines": [{"item_id": item["id"], "unit_price": "7"}]}, headers=h),
                  lambda h: self.c.post(f"{R}/{mine['id']}/submit", headers=h),
                  lambda h: self.c.post(f"{R}/{mine['id']}/cancel", json={"reason": "x"}, headers=h)]
        for w in writes:
            r = w(self.acct)
            self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
            r = w(self.sales2)                                                                              # another SALES user: not the owner
            self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_NOT_OWNER"))
        self.assertEqual(self.get(mine["id"]), mine)                                                        # none of the refused writes changed anything
        for h in (self.acct, self.sales2, self.admin):                                                      # everybody reads
            self.assertEqual(self.get(mine["id"], headers=h)["id"], mine["id"])
            self.assertEqual(self.c.get(f"{R}/{mine['id']}/pricing", headers=h).status_code, 200)
        self.assertIn(mine["id"], [x["id"] for x in self.c.get(R, params={"page_size": 200}, headers=self.sales2).json()["items"]])
        r = self.c.patch(f"{R}/{mine['id']}", json={"notes": "admin may", "updated_at": mine["updated_at"]}, headers=self.admin)  # ADMIN: any request
        self.assertEqual(r.status_code, 200, r.text)
        r = self.c.post(f"{R}/{mine['id']}/submit", headers=self.sales)                                       # the owner may
        self.assertEqual(r.status_code, 200, r.text)
        r = self.c.get(f"{R}/{mine['id']}", headers={})
        self.assertEqual(r.status_code, 401)

    # ------------------------------------------------------------------ T-TENANT
    def test_tenant_isolation(self):
        d = self.ready_request()
        item = d["items"][0]
        ghost, ghost_item = str(uuid.uuid4()), str(uuid.uuid4())
        pairs = [(lambda rid, h: self.c.get(f"{R}/{rid}", headers=h)),
                 (lambda rid, h: self.c.patch(f"{R}/{rid}", json={"notes": "x", "updated_at": d["updated_at"]}, headers=h)),
                 (lambda rid, h: self.c.post(f"{R}/{rid}/submit", headers=h)),
                 (lambda rid, h: self.c.post(f"{R}/{rid}/cancel", json={"reason": "x"}, headers=h)),
                 (lambda rid, h: self.c.post(f"{R}/{rid}/items", json=self.item(product_id=self.b_prod), headers=h)),
                 (lambda rid, h: self.c.get(f"{R}/{rid}/pricing", headers=h)),
                 (lambda rid, h: self.c.post(f"{R}/{rid}/pricing", json={"updated_at": d["updated_at"], "lines": [{"item_id": item["id"], "unit_price": "1"}]}, headers=h))]
        for call in pairs:
            a, b = call(d["id"], self.other), call(ghost, self.other)
            self.assertEqual((a.status_code, err(a)), (404, err(b)))
            self.assertEqual(err(a), {"code": "NOT_FOUND", "message": "Not found", "details": {"resource": "purchase_request"}})
        for call in ((lambda i: self.c.patch(f"{RI}/{i}", json={"quantity": "2", "updated_at": item["updated_at"]}, headers=self.other)),
                     (lambda i: self.c.delete(f"{RI}/{i}", headers=self.other))):
            a, b = call(item["id"]), call(ghost_item)
            self.assertEqual((a.status_code, err(a)), (404, err(b)))
        self.assertEqual(self.c.get(R, params={"page_size": 200}, headers=self.other).json()["items"], [])
        self.assertEqual(self.get(d["id"]), d)

    # ------------------------------------------------------------------ T-RACE
    def test_submit_racing_item_inserts(self):
        d = self.ready_request()
        results, bar = [], threading.Barrier(11)

        def adder():
            c = TestClient(self.c.app)
            bar.wait()
            results.append(c.post(f"{R}/{d['id']}/items", json=self.item(), headers=self.admin).status_code)

        def submitter():
            c = TestClient(self.c.app)
            bar.wait()
            results.append(("submit", c.post(f"{R}/{d['id']}/submit", headers=self.admin).status_code))
        ts = [threading.Thread(target=adder) for _ in range(10)] + [threading.Thread(target=submitter)]
        [t.start() for t in ts]; [t.join() for t in ts]
        codes = [x for x in results if not isinstance(x, tuple)]
        self.assertTrue(set(codes) <= {201, 409}, results)                                                   # no 500, no deadlock
        self.assertIn(("submit", 200), results)
        final = self.get(d["id"])
        self.assertEqual(final["status"], "SUBMITTED")
        self.assertEqual(len(final["items"]), 1 + codes.count(201))                                          # no item slipped in after submit
        self.assertEqual(final["grand_total"], str(10_000 * len(final["items"])))
        late = self.c.post(f"{R}/{d['id']}/items", json=self.item(), headers=self.admin)
        self.assertEqual(late.status_code, 409)

    def test_parallel_item_inserts_keep_totals_correct(self):
        d = self.mk()
        out, bar = [], threading.Barrier(8)

        def go():
            c = TestClient(self.c.app)
            bar.wait()
            for _ in range(3):
                out.append(c.post(f"{R}/{d['id']}/items", json=self.item(quantity="1", unit_price="100"), headers=self.admin).status_code)
        ts = [threading.Thread(target=go) for _ in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(set(out), {201})
        final = self.get(d["id"])
        self.assertEqual((len(final["items"]), final["subtotal"], final["grand_total"]), (24, "2400", "2400"))

    def test_submit_twice_in_parallel_only_one_succeeds(self):
        d = self.ready_request()
        res, bar = [], threading.Barrier(5)

        def go():
            c = TestClient(self.c.app)
            bar.wait()
            res.append(c.post(f"{R}/{d['id']}/submit", headers=self.admin).status_code)
        ts = [threading.Thread(target=go) for _ in range(5)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted(res), [200, 409, 409, 409, 409])

    # ------------------------------------------------------------------ T-AUDIT and GET /audit-logs
    def audit_rows(self, **params):
        r = self.c.get(f"{API}/audit-logs", params={"page_size": 200, **params}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_audit_rows_for_every_event_and_audit_logs_endpoint(self):
        d = self.mk(headers=self.sales, items=[self.item(unit_price="0")])
        rid, item = d["id"], d["items"][0]
        self.c.patch(f"{R}/{rid}", json={"notes": "n1", "updated_at": d["updated_at"]}, headers=self.sales)
        extra = self.add(rid, headers=self.sales)["item"]
        self.c.patch(f"{RI}/{item['id']}", json={"quantity": "3", "updated_at": item["updated_at"]}, headers=self.sales)
        v = self.c.get(f"{R}/{rid}/pricing", headers=self.sales).json()["data"]
        self.c.post(f"{R}/{rid}/pricing", json={"updated_at": v["updated_at"], "lines": [{"item_id": item["id"], "unit_price": "50", "tax_amount": "5"}]}, headers=self.sales)
        self.c.delete(f"{RI}/{extra['id']}", headers=self.sales)
        self.assertEqual(self.c.post(f"{R}/{rid}/submit", headers=self.sales).status_code, 200)
        self.c.post(f"{R}/{rid}/cancel", json={"reason": "no longer needed"}, headers=self.admin)
        rows = self.audit_rows(entity_id=rid)["items"]
        seq = [(x["action"], x["entity_type"]) for x in reversed(rows)]
        self.assertEqual(seq, [("CREATE", "PURCHASE_REQUEST"), ("UPDATE", "PURCHASE_REQUEST"), ("SUBMIT", "PURCHASE_REQUEST"), ("CANCEL", "PURCHASE_REQUEST")])
        by = {x["action"]: x for x in rows}
        self.assertEqual(by["CREATE"]["new_data"]["item_count"], 1)
        self.assertEqual((by["UPDATE"]["old_data"], by["UPDATE"]["new_data"]), ({"notes": None}, {"notes": "n1"}))
        self.assertEqual((by["SUBMIT"]["old_data"], by["SUBMIT"]["new_data"]["status"]), ({"status": "DRAFT"}, "SUBMITTED"))
        self.assertEqual((by["CANCEL"]["description"], by["CANCEL"]["new_data"], by["CANCEL"]["old_data"]), ("no longer needed", {"status": "CANCELLED"}, {"status": "SUBMITTED"}))
        self.assertEqual(by["CREATE"]["user_id"], d["created_by"])
        self.assertTrue(by["CANCEL"]["user_id"] != d["created_by"])                                         # the canceller (admin) is recorded
        irows = self.audit_rows(entity_id=item["id"])["items"]
        self.assertEqual([x["action"] for x in reversed(irows)], ["UPDATE", "UPDATE"])                      # items made with the request have no own CREATE row (13)
        price = irows[0]
        self.assertEqual((price["old_data"], price["new_data"]), ({"unit_price": "0", "tax_amount": "0"}, {"unit_price": "50", "tax_amount": "5"}))
        qty = irows[1]
        self.assertEqual((qty["old_data"]["quantity"], qty["new_data"]["quantity"]), ("10.000", "3.000"))
        drows = self.audit_rows(entity_id=extra["id"])["items"]
        self.assertEqual([x["action"] for x in reversed(drows)], ["CREATE", "DELETE"])
        self.assertEqual((drows[0]["old_data"]["id"], drows[0]["new_data"]), (extra["id"], None))
        # filters
        self.assertEqual({x["action"] for x in self.audit_rows(entity_id=rid, action="CANCEL")["items"]}, {"CANCEL"})
        self.assertEqual({x["entity_type"] for x in self.audit_rows(entity_id=item["id"], entity_type="PURCHASE_REQUEST_ITEM")["items"]}, {"PURCHASE_REQUEST_ITEM"})
        self.assertEqual(self.audit_rows(entity_id=rid, actor_id=d["created_by"])["total"], 3)
        self.assertEqual(self.audit_rows(entity_id=rid, created_to="2000-01-01")["total"], 0)
        self.assertEqual(len(self.audit_rows(entity_id=rid, page_size=2)["items"]), 2)
        ordered = [x["created_at"] for x in self.audit_rows(entity_id=rid)["items"]]
        self.assertEqual(ordered, sorted(ordered, reverse=True))
        for q in ({"entity_type": "X"}, {"action": "X"}, {"entity_id": "x"}, {"actor_id": "x"}, {"created_from": "x"}):
            self.assertEqual(self.c.get(f"{API}/audit-logs", params=q, headers=self.admin).status_code, 422, q)
        for h in (self.sales, self.acct):
            r = self.c.get(f"{API}/audit-logs", headers=h)
            self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
        self.assertEqual(self.c.get(f"{API}/audit-logs", headers=self.other).json()["items"].count(rows[0]), 0)   # other organization sees none of it
        text = str(rows) + str(irows) + str(drows)
        for secret in ("password", "token", "hash"):
            self.assertNotIn(secret, text.lower())

    def test_audit_is_written_in_the_same_transaction(self):
        from unittest import mock
        before = support.scalar("SELECT count(*) FROM purchase_requests")
        first = self.mk()
        with mock.patch("app.requests_service.write_audit", side_effect=RuntimeError("boom")):
            r = self.c.post(R, json={"customer_id": self.cust, "items": [self.item()]}, headers=self.admin)
        self.assertEqual(r.status_code, 500)
        self.assertEqual(int(support.scalar("SELECT count(*) FROM purchase_requests")), int(before) + 1)      # only `first`: no header, no items
        nxt = self.mk()
        self.assertEqual(int(nxt["request_number"].split("-")[1]), int(first["request_number"].split("-")[1]) + 1)   # the number was given back
        d = self.ready_request()
        with mock.patch("app.requests_service.write_audit", side_effect=RuntimeError("boom")):
            r = self.c.post(f"{R}/{d['id']}/submit", headers=self.admin)
        self.assertEqual(r.status_code, 500)
        self.assertEqual(self.get(d["id"])["status"], "DRAFT")
        rc, _, _ = pg.psql(support.DB, f"UPDATE audit_logs SET description = 'x' WHERE entity_id = '{d['id']}'")
        self.assertNotEqual(rc, 0)                                                                           # append-only, enforced by the database

    # ------------------------------------------------------------------ T-E2E
    def test_end_to_end(self):
        h = self.sales
        cust = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": "e2e-" + uuid.uuid4().hex[:8], "national_id": "۱۲۳۴۵۶"}, headers=h)
        self.assertEqual(cust.status_code, 201)
        prod = self.new_product()
        self.assertEqual(self.c.get(f"{API}/products/{prod['id']}/specifications", headers=h).json()["data"]["fields"][0]["code"], "DIAMETER")
        d = self.mk(headers=h, customer_id=cust.json()["data"]["id"], notes="e2e", items=[
            {"product_id": prod["id"], "quantity": "10", "bundle_count": "2", "estimated_weight": "1250.5", "specifications": self.spec},
            {"product_id": prod["id"], "quantity": "5.5", "unit_price": "100", "specifications": [{"field_id": self.f_diam, "value": "1/2"}, {"field_id": self.f_thick, "value": "2.50"}]}])
        v = self.c.get(f"{R}/{d['id']}/pricing", headers=h).json()["data"]
        r = self.c.post(f"{R}/{d['id']}/pricing", json={"updated_at": v["updated_at"], "lines": [{"item_id": d["items"][0]["id"], "unit_price": "125000", "discount_amount": "1000", "tax_amount": "500"}]}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        got = self.get(d["id"], headers=self.acct)
        self.assertEqual((got["items"][0]["line_total"], got["items"][1]["line_total"], got["grand_total"]), ("1249500", "550", "1250050"))
        self.assertEqual((got["items"][0]["estimated_weight"], got["items"][0]["bundle_count"]), ("1250.500", "2"))
        s = self.c.post(f"{R}/{d['id']}/submit", headers=h)
        self.assertEqual((s.status_code, s.json()["data"]["status"]), (200, "SUBMITTED"))
        rows = self.audit_rows(entity_id=d["id"])["items"]
        self.assertEqual([x["action"] for x in reversed(rows)], ["CREATE", "SUBMIT"])
        c = self.c.post(f"{R}/{d['id']}/cancel", json={"reason": "e2e done"}, headers=h)
        self.assertEqual((c.status_code, c.json()["data"]["status"]), (200, "CANCELLED"))
        self.assertEqual(self.audit_rows(entity_id=d["id"])["total"], 3)


if __name__ == "__main__":
    unittest.main()
