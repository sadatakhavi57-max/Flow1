import threading
import unittest
import uuid

from fastapi.testclient import TestClient

from tests import support

C = "/api/v1/customers"


def uniq(prefix="cust"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def err(r):
    e = dict(r.json()["error"])
    e.pop("request_id")
    return e


@unittest.skipUnless(support.ready(), "SKIPPED: needs PostgreSQL (psql) and TF_SQL_DIR")
class CustomersHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.build_db()
        cls.c = TestClient(support.make_app())
        cls.admin, cls.sales, cls.acct = (support.headers(u) for u in ("admin", "sales", "accounting"))
        cls.other = support.headers("admin", "OTHER")

    def create(self, headers=None, **kw):
        body = {"customer_type": "COMPANY", "name": uniq(), **kw}
        r = self.c.post(C, json=body, headers=headers or self.admin)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]

    def test_create_get_and_envelope(self):
        d = self.create(national_id="۱۲۳ ۴۵", economic_code="   ", mobile="0912")
        self.assertEqual((d["national_id"], d["economic_code"], d["credit_limit"], d["is_active"]), ("12345", None, "0", True))
        self.assertTrue(d["created_at"].endswith("Z") and len(d["created_at"]) == 27)
        r = self.c.get(f"{C}/{d['id']}", headers=self.admin)
        self.assertEqual((r.status_code, r.json()["data"], r.json()["request_id"] == r.headers["X-Request-Id"]), (200, d, True))

    def test_duplicate_identifier_but_same_name_allowed(self):
        nid = str(uuid.uuid4().int)[:12]
        self.create(national_id=nid, name="same-name-allowed")
        r = self.c.post(C, json={"customer_type": "INDIVIDUAL", "name": "x", "national_id": nid}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]), (409, "DUPLICATE_IDENTIFIER", {"field": "national_id"}))
        r = self.c.post(C, json={"customer_type": "COMPANY", "name": "same-name-allowed"}, headers=self.admin)
        self.assertEqual(r.status_code, 201)
        code = str(uuid.uuid4().int)[:10]
        self.create(economic_code=code)
        r = self.c.post(C, json={"customer_type": "COMPANY", "name": "y", "economic_code": f" {code[:5]} {code[5:]} "}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["details"]), (409, {"field": "economic_code"}))

    def test_validation(self):
        bad = [{"name": "x"}, {"customer_type": "X", "name": "x"}, {"customer_type": "COMPANY", "name": " "},
               {"customer_type": "COMPANY", "name": "x", "organization_id": str(uuid.uuid4())},
               {"customer_type": "COMPANY", "name": "x", "id": str(uuid.uuid4())},
               {"customer_type": "COMPANY", "name": "x", "is_active": "yes"}]
        for b in bad:
            r = self.c.post(C, json=b, headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"), b)
        for v in ("1.5", "-1", 5, "1e3"):
            r = self.c.post(C, json={"customer_type": "COMPANY", "name": "x", "credit_limit": v}, headers=self.admin)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "INVALID_MONEY"), v)
        r = self.c.get(f"{C}/not-a-uuid", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"))

    def test_role_matrix(self):
        body = {"customer_type": "COMPANY", "name": uniq()}
        self.assertEqual(self.c.post(C, json=body, headers=self.acct).status_code, 403)
        self.assertEqual(err(self.c.post(C, json=body, headers=self.acct))["code"], "FORBIDDEN_ROLE")
        self.assertEqual(self.c.post(C, json={**body, "name": uniq()}, headers=self.sales).status_code, 201)
        d = self.create()
        self.assertEqual(self.c.get(f"{C}/{d['id']}", headers=self.acct).status_code, 200)
        r = self.c.patch(f"{C}/{d['id']}", json={"name": "z", "updated_at": d["updated_at"]}, headers=self.acct)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
        self.assertEqual(self.c.get(C).status_code, 401)

    def test_list_filters_pagination_and_order(self):
        tag = uniq("flt")
        a = self.create(name=f"{tag}-b", customer_type="INDIVIDUAL", mobile="09121234567")
        b = self.create(name=f"{tag}-a", national_id=str(uuid.uuid4().int)[:12])
        r = self.c.get(C, params={"search": tag}, headers=self.admin).json()
        self.assertEqual([i["name"] for i in r["items"]], [f"{tag}-a", f"{tag}-b"])           # name ASC
        self.assertEqual((r["total"], r["page"], r["page_size"]), (2, 1, 50))
        self.assertEqual(r["request_id"] != "", True)
        r = self.c.get(C, params={"search": tag.upper(), "customer_type": "INDIVIDUAL"}, headers=self.admin).json()
        self.assertEqual([i["id"] for i in r["items"]], [a["id"]])
        r = self.c.get(C, params={"search": "۰۹۱۲۱۲۳۴۵۶۷"}, headers=self.admin).json()           # Persian digits find the mobile
        self.assertIn(a["id"], [i["id"] for i in r["items"]])
        r = self.c.get(C, params={"search": tag, "page_size": 1, "page": 2}, headers=self.admin).json()
        self.assertEqual(([i["id"] for i in r["items"]], r["total"]), ([a["id"]], 2))
        lit = self.create(name=f"100%{tag}")                                                    # LIKE characters are literal
        self.create(name=f"100x{tag}")
        r = self.c.get(C, params={"search": f"100%{tag}"}, headers=self.admin).json()
        self.assertEqual([i["id"] for i in r["items"]], [lit["id"]])
        for q in ({"page_size": 201}, {"page": 0}, {"is_active": "maybe"}, {"customer_type": "X"}):
            self.assertEqual(self.c.get(C, params=q, headers=self.admin).status_code, 422, q)
        self.c.patch(f"{C}/{b['id']}", json={"is_active": False, "updated_at": b["updated_at"]}, headers=self.admin)
        r = self.c.get(C, params={"search": tag, "is_active": "false"}, headers=self.admin).json()
        self.assertEqual([i["id"] for i in r["items"]], [b["id"]])

    def test_patch_optimistic_and_noop(self):
        d = self.create()
        r = self.c.patch(f"{C}/{d['id']}", json={"name": "renamed", "updated_at": d["updated_at"]}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        new = r.json()["data"]
        self.assertEqual(new["name"], "renamed")
        self.assertNotEqual(new["updated_at"], d["updated_at"])
        r = self.c.patch(f"{C}/{d['id']}", json={"name": "again", "updated_at": d["updated_at"]}, headers=self.admin)   # stale
        self.assertEqual((r.status_code, err(r)["code"]), (409, "STALE_UPDATE"))
        self.assertEqual(err(r)["details"]["current"], new)
        r = self.c.patch(f"{C}/{d['id']}", json={"name": "renamed", "updated_at": new["updated_at"]}, headers=self.admin)  # no-op
        self.assertEqual((r.status_code, r.json()["data"]["updated_at"]), (200, new["updated_at"]))
        for bad in ({"name": "x"}, {"name": "x", "updated_at": "yesterday"}, {"id": d["id"], "updated_at": new["updated_at"]}):
            self.assertEqual(self.c.patch(f"{C}/{d['id']}", json=bad, headers=self.admin).status_code, 422, bad)

    def test_two_stale_patches_one_wins(self):
        d = self.create()
        res, bar = [], threading.Barrier(2)

        def go(name):
            c = TestClient(self.c.app)
            bar.wait()
            res.append(c.patch(f"{C}/{d['id']}", json={"name": name, "updated_at": d["updated_at"]}, headers=self.admin).status_code)
        ts = [threading.Thread(target=go, args=(f"race-{i}-{uniq()}",)) for i in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted(res), [200, 409])

    def test_tenant_isolation(self):
        d = self.create()
        ghost = str(uuid.uuid4())
        a = self.c.get(f"{C}/{d['id']}", headers=self.other)
        b = self.c.get(f"{C}/{ghost}", headers=self.other)
        self.assertEqual((a.status_code, err(a)), (404, err(b)))
        self.assertEqual(err(a)["code"], "NOT_FOUND")
        p1 = self.c.patch(f"{C}/{d['id']}", json={"name": "hack", "updated_at": d["updated_at"]}, headers=self.other)
        p2 = self.c.patch(f"{C}/{ghost}", json={"name": "hack", "updated_at": d["updated_at"]}, headers=self.other)
        self.assertEqual((p1.status_code, err(p1)), (404, err(p2)))
        ids = [i["id"] for i in self.c.get(C, params={"page_size": 200}, headers=self.other).json()["items"]]
        self.assertNotIn(d["id"], ids)
        self.assertEqual(self.c.get(f"{C}/{d['id']}", headers=self.admin).json()["data"]["name"], d["name"])

    def test_audit_rows(self):
        d = self.create()
        self.c.patch(f"{C}/{d['id']}", json={"name": "audited", "credit_limit": "500", "updated_at": d["updated_at"]}, headers=self.admin)
        out = support.scalar(f"SELECT action||':'||entity_type||':'||coalesce(old_data::text,'-')||':'||coalesce(new_data->>'name','-') FROM audit_logs WHERE entity_id = '{d['id']}' ORDER BY created_at, id")
        lines = out.splitlines()
        self.assertEqual(len(lines), 2, out)
        self.assertTrue(lines[0].startswith("CREATE:CUSTOMER:-:"), lines[0])
        self.assertTrue(lines[1].startswith("UPDATE:CUSTOMER:") and lines[1].endswith(":audited"), lines[1])
        self.assertIn(d["name"], lines[1]); self.assertIn('"credit_limit": "0"', lines[1])
        self.assertEqual(support.scalar(f"SELECT count(*) FROM audit_logs WHERE entity_id = '{d['id']}' AND (old_data::text ~* 'password|token' OR new_data::text ~* 'password|token')"), "0")


if __name__ == "__main__":
    unittest.main()
