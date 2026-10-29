import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests import support
from tradeflow_core import numbering

R = "/api/v1/purchase-requests"
RI = "/api/v1/purchase-request-items"


def err(r):
    e = dict(r.json()["error"])
    e.pop("request_id")
    return e


def today():
    return numbering.tehran_today(datetime.now(timezone.utc))


@unittest.skipUnless(support.ready(), "SKIPPED: needs PostgreSQL (psql) and TF_SQL_DIR")
class RequestsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.build_db()
        cls.c = TestClient(support.make_app())
        cls.admin, cls.sales, cls.sales2, cls.acct = (support.headers(u) for u in ("admin", "sales", "sales2", "accounting"))
        cls.other = support.headers("admin", "OTHER")
        q = support.scalar
        demo = "(SELECT id FROM organizations WHERE code = 'DEMO')"
        cls.cust = q(f"SELECT id FROM customers WHERE organization_id = {demo} LIMIT 1")
        cls.prod = q("SELECT id FROM products WHERE code = 'GAS-PIPE-2IN'")
        cls.kg = q(f"SELECT id FROM units WHERE code = 'KG' AND organization_id = {demo}")
        cls.cat = q("SELECT id FROM product_categories WHERE code = 'PIPE_PROFILE'")
        fid = lambda code: q(f"SELECT f.id FROM product_specification_fields f WHERE f.code = '{code}' AND f.organization_id = {demo}")
        cls.f_diam, cls.f_thick, cls.f_grade, cls.f_inactive, cls.f_other = (fid(c) for c in ("DIAMETER", "THICKNESS_MM", "GRADE", "INACTIVE_F", "OTHER_F"))
        cls.f_b = q("SELECT id FROM product_specification_fields WHERE code = 'B_F'")
        cls.b_cust = q("SELECT id FROM customers WHERE name = 'B-customer'")
        cls.b_prod = q("SELECT id FROM products WHERE code = 'B-PROD'")
        cls.b_unit = q("SELECT id FROM units WHERE code = 'BKG'")
        cls.spec = [{"field_id": cls.f_diam, "value": "2"}]

    # ---- helpers
    def item(self, **kw):
        return {"product_id": self.prod, "quantity": "10", "unit_price": "1000", "specifications": self.spec, **kw}

    def mk(self, headers=None, items=None, **kw):
        body = {"customer_id": self.cust, **kw}
        if items is not None:
            body["items"] = items
        r = self.c.post(R, json=body, headers=headers or self.admin)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]

    def add(self, rid, headers=None, **kw):
        r = self.c.post(f"{R}/{rid}/items", json=self.item(**kw), headers=headers or self.admin)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]

    def get(self, rid, headers=None):
        r = self.c.get(f"{R}/{rid}", headers=headers or self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]

    def new_product(self, **kw):
        r = self.c.post("/api/v1/products", json={"code": "T-" + uuid.uuid4().hex[:10], "name": "T-" + uuid.uuid4().hex[:10],
                                                  "category_id": self.cat, "default_unit_id": self.kg, **kw}, headers=self.admin)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]


class RequestsCore(RequestsBase):
    # ------------------------------------------------------------------ T-NUM, create
    def test_create_empty_number_format_and_sequence(self):
        a = self.mk()
        series = numbering.series_for(datetime.now(timezone.utc))
        sa, na = numbering.parse_request_number(a["request_number"])
        self.assertEqual(sa, series)
        self.assertEqual((a["status"], a["items"], a["subtotal"], a["grand_total"], a["requested_delivery_date"]), ("DRAFT", [], "0", "0", None))
        self.assertEqual(a["created_by"], a["updated_by"])
        self.assertEqual(a["customer"]["id"], self.cust)
        b = self.mk()
        self.assertEqual(numbering.parse_request_number(b["request_number"]), (series, na + 1))
        self.assertEqual(self.get(a["id"])["request_number"], a["request_number"])

    def test_parallel_creations_get_unique_numbers(self):
        out, bar = [], threading.Barrier(8)

        def go():
            c = TestClient(self.c.app)
            bar.wait()
            for _ in range(3):
                r = c.post(R, json={"customer_id": self.cust}, headers=self.admin)
                out.append((r.status_code, r.json()["data"]["request_number"] if r.status_code == 201 else r.text))
        ts = [threading.Thread(target=go) for _ in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted({s for s, _ in out}), [201])
        nums = [n for _, n in out]
        self.assertEqual((len(nums), len(set(nums))), (24, 24))

    def test_failed_creation_gives_its_number_back(self):
        a = self.mk()
        bad = self.c.post(R, json={"customer_id": self.cust, "items": [self.item(product_id=self.b_prod)]}, headers=self.admin)
        self.assertEqual((bad.status_code, err(bad)["code"]), (422, "REFERENCE_NOT_FOUND"))
        b = self.mk()
        self.assertEqual(numbering.parse_request_number(b["request_number"])[1], numbering.parse_request_number(a["request_number"])[1] + 1)

    def test_create_with_items_computes_money_like_the_contract(self):
        d = self.mk(items=[self.item(quantity="10.000", unit_price="125000", discount_amount="1000", tax_amount="500"),
                           self.item(quantity="2.5", unit_price="333")])
        i1, i2 = d["items"]
        self.assertEqual((i1["quantity"], i1["line_total"], i1["bundle_count"], i1["estimated_weight"]), ("10.000", "1249500", "0", None))
        self.assertEqual((i2["quantity"], i2["line_total"]), ("2.500", "833"))                            # 832.5 -> HALF_UP
        self.assertEqual((d["subtotal"], d["discount_total"], d["tax_total"], d["grand_total"]), ("1250833", "1000", "500", "1250333"))
        self.assertEqual(i1["unit"]["code"], "KG")                                                       # unit_id defaulted from the product (D2)
        self.assertEqual(i1["product"]["code"], "GAS-PIPE-2IN")
        self.assertEqual([x["id"] for x in d["items"]], [x["id"] for x in self.get(d["id"])["items"]])   # stable insertion order

    def test_create_validation_and_references(self):
        for body in ({}, {"customer_id": self.cust, "status": "SUBMITTED"}, {"customer_id": self.cust, "request_number": "1405-000001"},
                     {"customer_id": self.cust, "organization_id": self.cust}, {"customer_id": "x"}, {"customer_id": self.cust, "items": "x"},
                     {"customer_id": self.cust, "items": [{"quantity": "1"}]},
                     {"customer_id": self.cust, "items": [self.item(line_total="5")]}):
            r = self.c.post(R, json=body, headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"), body)
        a = self.c.post(R, json={"customer_id": self.b_cust}, headers=self.admin)
        b = self.c.post(R, json={"customer_id": str(uuid.uuid4())}, headers=self.admin)
        self.assertEqual((a.status_code, err(a)), (422, err(b)))
        self.assertEqual(err(a)["code"], "REFERENCE_NOT_FOUND")
        support.scalar("INSERT INTO customers (organization_id, customer_type, name, is_active) SELECT id, 'COMPANY', 'inactive-cust', FALSE FROM organizations WHERE code = 'DEMO' ON CONFLICT DO NOTHING")
        inactive = support.scalar("SELECT id FROM customers WHERE name = 'inactive-cust'")
        r = self.c.post(R, json={"customer_id": inactive}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "INACTIVE_REFERENCE"))
        for bad_item in (self.item(unit_id=self.b_unit), self.item(unit_id=str(uuid.uuid4())), self.item(product_id=str(uuid.uuid4()))):
            r = self.c.post(R, json={"customer_id": self.cust, "items": [bad_item]}, headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "REFERENCE_NOT_FOUND"))

    def test_delivery_date_rules(self):
        t = today()
        self.assertEqual(self.mk(requested_delivery_date=t.isoformat())["requested_delivery_date"], t.isoformat())
        self.assertEqual(self.mk(requested_delivery_date=(t + timedelta(days=30)).isoformat())["requested_delivery_date"], (t + timedelta(days=30)).isoformat())
        for bad in ((t - timedelta(days=1)).isoformat(), "2026-02-30", "x", 20261115):
            r = self.c.post(R, json={"customer_id": self.cust, "requested_delivery_date": bad}, headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"), bad)
        d = self.mk()
        r = self.c.patch(f"{R}/{d['id']}", json={"requested_delivery_date": (t - timedelta(days=1)).isoformat(), "updated_at": d["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"))

    # ------------------------------------------------------------------ T-MONEY, T-CAP (through the API)
    def test_money_and_quantity_errors(self):
        d = self.mk()
        url = f"{R}/{d['id']}/items"

        def post(**kw):
            return self.c.post(url, json=self.item(**kw), headers=self.admin)
        for kw in ({"unit_price": "125000.00"}, {"unit_price": 125000}, {"unit_price": "-5"}, {"unit_price": "1e3"}, {"unit_price": ""},
                   {"discount_amount": "1.5"}, {"tax_amount": None}, {"quantity": "1.2345"}, {"quantity": "abc"}, {"estimated_weight": "-1"}):
            r = post(**kw)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "INVALID_MONEY"), kw)
        for kw in ({"quantity": "0"}, {"quantity": "0.000"}, {"bundle_count": "1" * 19}, {"bundle_count": "-1"}, {"bundle_count": "1.5"}):
            r = post(**kw)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"), kw)
        for kw in ({"unit_price": "100", "discount_amount": "1001"}, {"quantity": "999999999999999", "unit_price": "9" * 20}, {"unit_price": "9" * 20, "tax_amount": "9" * 20}):
            r = post(**kw)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "AMOUNT_OUT_OF_RANGE"), kw)
        self.assertEqual(post(bundle_count="9" * 18, unit_price="٢٥٠٠", quantity="۱.۵۰۰").status_code, 201)          # 18 digits ok; Persian digits normalized
        got = self.get(d["id"])["items"][0]
        self.assertEqual((got["unit_price"], got["quantity"], got["line_total"]), ("2500", "1.500", "3750"))
        self.assertEqual(len(self.get(d["id"])["items"]), 1)                                                          # every refused item left nothing behind

    # ------------------------------------------------------------------ T-SPEC
    def test_specification_snapshot(self):
        d = self.mk()
        r = self.c.post(f"{R}/{d['id']}/items", json=self.item(specifications=[
            {"field_id": self.f_grade, "value": "  ST37 "}, {"field_id": self.f_thick, "value": "۲٫۵۰"}, {"field_id": self.f_diam, "value": "2"}]), headers=self.admin)
        self.assertEqual(r.status_code, 201, r.text)
        snap = r.json()["data"]["item"]["specifications"]
        self.assertEqual(snap, [{"field_id": self.f_grade, "field_code": "GRADE", "field_name": "گرید", "data_type": "TEXT", "value": "ST37"},
                                {"field_id": self.f_thick, "field_code": "THICKNESS_MM", "field_name": "ضخامت (mm)", "data_type": "DECIMAL", "value": "2.5"},
                                {"field_id": self.f_diam, "field_code": "DIAMETER", "field_name": "قطر", "data_type": "SELECT", "value": "2"}])
        support.scalar(f"UPDATE product_specification_fields SET name = 'renamed later', options = '[\"9\"]' WHERE id = '{self.f_diam}'")
        try:
            again = self.get(d["id"])["items"][0]["specifications"]
        finally:
            support.scalar(f"UPDATE product_specification_fields SET name = 'قطر', options = '[\"1/2\",\"1\",\"2\",\"3\"]' WHERE id = '{self.f_diam}'")
        self.assertEqual(again, snap)                                                                      # snapshot never follows master data

    def test_specification_errors(self):
        d = self.mk()
        url = f"{R}/{d['id']}/items"
        ghost = str(uuid.uuid4())
        cases = [([{"field_id": ghost, "value": "x"}], "UNKNOWN_FIELD", ghost),
                 ([{"field_id": self.f_b, "value": "x"}], "UNKNOWN_FIELD", self.f_b),                       # another organization's field
                 ([{"field_id": self.f_other, "value": "x"}], "NOT_APPLICABLE", self.f_other),
                 ([{"field_id": self.f_inactive, "value": "x"}], "INACTIVE_FIELD", self.f_inactive),
                 ([{"field_id": self.f_diam, "value": "2"}, {"field_id": self.f_diam, "value": "3"}], "DUPLICATE_FIELD", self.f_diam),
                 ([{"field_id": self.f_thick, "value": "ABC"}], "INVALID_VALUE", self.f_thick),
                 ([{"field_id": self.f_thick, "value": "1,5"}], "INVALID_VALUE", self.f_thick),
                 ([{"field_id": self.f_thick, "value": 2.5}], "INVALID_VALUE", self.f_thick),
                 ([{"field_id": self.f_diam, "value": "9"}], "INVALID_VALUE", self.f_diam),
                 ([{"field_id": self.f_grade, "value": ""}], "INVALID_VALUE", self.f_grade),
                 ([{"field_id": self.f_grade, "value": None}], "INVALID_VALUE", self.f_grade)]
        for specs, reason, fid in cases:
            r = self.c.post(url, json=self.item(specifications=specs), headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]), (422, "SPECIFICATION_INVALID", [{"field_id": fid, "reason": reason}]), specs)
        for specs in ([{"field_id": self.f_diam, "value": "2", "field_code": "DIAMETER"}], [{"field_id": self.f_diam}], [{"field_id": "nope", "value": "2"}], {"a": 1}):
            r = self.c.post(url, json=self.item(specifications=specs), headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"), specs)
        self.assertEqual(self.get(d["id"])["items"], [])
        self.assertEqual(self.c.post(url, json=self.item(specifications=[]), headers=self.admin).status_code, 201)   # missing required is fine in DRAFT

    # ------------------------------------------------------------------ items: patch, delete, optimistic
    def test_item_patch_delete_totals_and_timestamps(self):
        d = self.mk()
        a = self.add(d["id"], quantity="2", unit_price="500")["item"]
        b = self.add(d["id"], quantity="1", unit_price="300")["item"]
        self.assertEqual(self.get(d["id"])["grand_total"], "1300")
        h0 = self.get(d["id"])["updated_at"]
        r = self.c.patch(f"{RI}/{a['id']}", json={"quantity": "4.5", "notes": "n", "updated_at": a["updated_at"]}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        new = r.json()["data"]
        self.assertEqual((new["item"]["quantity"], new["item"]["line_total"], new["request"]["grand_total"]), ("4.500", "2250", "2550"))
        self.assertNotEqual(new["request"]["updated_at"], h0)                                               # item writes bump the parent
        self.assertNotEqual(new["item"]["updated_at"], a["updated_at"])
        r = self.c.patch(f"{RI}/{a['id']}", json={"quantity": "9", "updated_at": a["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]["current"]), (409, "STALE_UPDATE", new["item"]))
        r = self.c.patch(f"{RI}/{a['id']}", json={"product_id": self.b_prod, "updated_at": new["item"]["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"))
        r = self.c.patch(f"{RI}/{a['id']}", json={"product_id": self.prod, "quantity": "4.5", "updated_at": new["item"]["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, r.json()["data"]["item"]["updated_at"]), (200, new["item"]["updated_at"]))   # same product + same values = no-op
        r = self.c.patch(f"{RI}/{a['id']}", json={"specifications": [{"field_id": self.f_diam, "value": "3"}], "updated_at": new["item"]["updated_at"]}, headers=self.admin)
        self.assertEqual(r.json()["data"]["item"]["specifications"][0]["value"], "3")                       # replaces the whole snapshot
        for bad in ({"updated_at": "x"}, {"quantity": "1"}, {"unit_price": "1.5", "updated_at": new["item"]["updated_at"]}):
            self.assertIn(self.c.patch(f"{RI}/{a['id']}", json=bad, headers=self.admin).status_code, (422,))
        r = self.c.delete(f"{RI}/{b['id']}", headers=self.admin)
        self.assertEqual((r.status_code, r.json()["data"]["request"]["grand_total"]), (200, "2250"))
        self.assertEqual(self.c.delete(f"{RI}/{b['id']}", headers=self.admin).status_code, 404)
        self.assertEqual(len(self.get(d["id"])["items"]), 1)

    def test_header_patch_and_optimistic(self):
        d = self.mk()
        r = self.c.patch(f"{R}/{d['id']}", json={"notes": "hello", "updated_at": d["updated_at"]}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        new = r.json()["data"]
        self.assertEqual((new["notes"], new["updated_by"]), ("hello", d["created_by"]))
        r = self.c.patch(f"{R}/{d['id']}", json={"notes": "late", "updated_at": d["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (409, "STALE_UPDATE"))
        self.assertEqual(err(r)["details"]["current"]["notes"], "hello")
        r = self.c.patch(f"{R}/{d['id']}", json={"notes": "hello", "updated_at": new["updated_at"]}, headers=self.admin)
        self.assertEqual(r.json()["data"]["updated_at"], new["updated_at"])                                 # no-op keeps updated_at
        r = self.c.patch(f"{R}/{d['id']}", json={"customer_id": self.b_cust, "updated_at": new["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "REFERENCE_NOT_FOUND"))
        for bad in ({"status": "SUBMITTED", "updated_at": new["updated_at"]}, {"notes": "x"}, {"items": [], "updated_at": new["updated_at"]}):
            self.assertEqual(self.c.patch(f"{R}/{d['id']}", json=bad, headers=self.admin).status_code, 422)

    def test_two_stale_patches_one_wins(self):
        d = self.mk()
        res, bar = [], threading.Barrier(2)

        def go(i):
            c = TestClient(self.c.app)
            bar.wait()
            res.append(c.patch(f"{R}/{d['id']}", json={"notes": f"n{i}", "updated_at": d["updated_at"]}, headers=self.admin).status_code)
        ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted(res), [200, 409])

    # ------------------------------------------------------------------ pricing
    def test_pricing(self):
        d = self.mk(items=[self.item(unit_price="0", quantity="2"), self.item(unit_price="0", quantity="3")])
        i1, i2 = d["items"]
        v = self.c.get(f"{R}/{d['id']}/pricing", headers=self.acct).json()["data"]
        self.assertEqual((v["currency_unit"], v["status"], v["grand_total"], len(v["lines"])), ("RIAL", "DRAFT", "0", 2))
        self.assertEqual(set(v["lines"][0]), {"item_id", "product", "quantity", "unit_price", "discount_amount", "tax_amount", "line_total"})
        body = {"updated_at": v["updated_at"], "lines": [{"item_id": i1["id"], "unit_price": "100"}, {"item_id": i2["id"], "unit_price": "200", "tax_amount": "10"}]}
        r = self.c.post(f"{R}/{d['id']}/pricing", json=body, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        v2 = r.json()["data"]
        self.assertEqual([l["line_total"] for l in v2["lines"]], ["200", "610"])
        self.assertEqual((v2["subtotal"], v2["tax_total"], v2["grand_total"]), ("800", "10", "810"))
        self.assertNotEqual(v2["updated_at"], v["updated_at"])
        r = self.c.post(f"{R}/{d['id']}/pricing", json=body, headers=self.admin)                            # stale updated_at
        self.assertEqual((r.status_code, err(r)["code"]), (409, "STALE_UPDATE"))
        fresh = {"updated_at": v2["updated_at"]}
        r = self.c.post(f"{R}/{d['id']}/pricing", json={**fresh, "lines": [{"item_id": i1["id"], "unit_price": "999"}, {"item_id": i2["id"], "discount_amount": "999999"}]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "AMOUNT_OUT_OF_RANGE"))
        self.assertEqual(self.get(d["id"])["grand_total"], "810")                                           # all or nothing
        other = self.mk(items=[self.item()])["items"][0]
        for item_id in (other["id"], str(uuid.uuid4())):
            r = self.c.post(f"{R}/{d['id']}/pricing", json={**fresh, "lines": [{"item_id": item_id, "unit_price": "5"}]}, headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "REFERENCE_NOT_FOUND"))
        for bad in ({**fresh, "lines": []}, {**fresh, "lines": [{"item_id": i1["id"]}]}, {**fresh, "lines": [{"item_id": i1["id"], "unit_price": "1.5"}]},
                    {**fresh, "lines": [{"item_id": i1["id"], "unit_price": "1"}, {"item_id": i1["id"], "tax_amount": "1"}]}, {"lines": [{"item_id": i1["id"], "unit_price": "1"}]}):
            self.assertIn(self.c.post(f"{R}/{d['id']}/pricing", json=bad, headers=self.admin).status_code, (422,), bad)
        same = self.c.post(f"{R}/{d['id']}/pricing", json={**fresh, "lines": [{"item_id": i1["id"], "unit_price": "100"}]}, headers=self.admin)
        self.assertEqual((same.status_code, same.json()["data"]["updated_at"]), (200, v2["updated_at"]))      # no-op

    # ------------------------------------------------------------------ list
    def test_list_filters_and_item_count(self):
        t = today()
        tag = "flt-" + uuid.uuid4().hex[:8]
        cust = self.c.post("/api/v1/customers", json={"customer_type": "COMPANY", "name": tag}, headers=self.admin).json()["data"]["id"]
        a = self.mk(customer_id=cust, items=[self.item(), self.item()])
        b = self.mk(customer_id=cust)
        self.c.post(f"{R}/{b['id']}/cancel", json={"reason": "x"}, headers=self.admin)
        rows = self.c.get(R, params={"customer_id": cust}, headers=self.acct).json()
        self.assertEqual([x["id"] for x in rows["items"]], [b["id"], a["id"]])                               # created_at DESC, id DESC
        self.assertEqual((rows["total"], rows["items"][1]["item_count"], rows["items"][0]["item_count"]), (2, 2, 0))
        self.assertNotIn("items", rows["items"][0])
        self.assertEqual([x["id"] for x in self.c.get(R, params={"customer_id": cust, "status": "CANCELLED"}, headers=self.admin).json()["items"]], [b["id"]])
        self.assertEqual(self.c.get(R, params={"search": tag}, headers=self.admin).json()["total"], 2)
        self.assertEqual([x["id"] for x in self.c.get(R, params={"search": a["request_number"]}, headers=self.admin).json()["items"]], [a["id"]])
        self.assertEqual(self.c.get(R, params={"customer_id": cust, "created_from": t.isoformat(), "created_to": t.isoformat()}, headers=self.admin).json()["total"], 2)
        self.assertEqual(self.c.get(R, params={"customer_id": cust, "created_to": (t - timedelta(days=1)).isoformat()}, headers=self.admin).json()["total"], 0)
        self.assertEqual(self.c.get(R, params={"customer_id": cust, "created_from": (t + timedelta(days=1)).isoformat()}, headers=self.admin).json()["total"], 0)
        self.assertEqual(len(self.c.get(R, params={"customer_id": cust, "page_size": 1}, headers=self.admin).json()["items"]), 1)
        for q in ({"status": "X"}, {"customer_id": "x"}, {"created_from": "yesterday"}, {"page_size": 0}):
            self.assertEqual(self.c.get(R, params=q, headers=self.admin).status_code, 422, q)


if __name__ == "__main__":
    unittest.main()
