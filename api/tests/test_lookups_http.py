import unittest
import uuid

from fastapi.testclient import TestClient

from tests import support

API = "/api/v1"


def err(r):
    e = dict(r.json()["error"])
    e.pop("request_id")
    return e


@unittest.skipUnless(support.ready(), "SKIPPED: needs PostgreSQL (psql) and TF_SQL_DIR")
class LookupsAndOrganization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.build_db()
        cls.c = TestClient(support.make_app())
        cls.hs = {u: support.headers(u) for u in ("admin", "sales", "accounting")}
        cls.other = support.headers("admin", "OTHER")
        support.scalar("INSERT INTO product_categories (organization_id, name, code, is_active) SELECT id, 'قدیمی', 'LOOKUP_OLD', FALSE FROM organizations WHERE code = 'DEMO' ON CONFLICT DO NOTHING")
        support.scalar("INSERT INTO units (organization_id, name, code, unit_type, is_active) SELECT id, 'قدیمی', 'LOOKUP_OLDU', 'AREA', FALSE FROM organizations WHERE code = 'DEMO' ON CONFLICT DO NOTHING")

    def test_all_roles_read_lookups(self):
        for u, h in self.hs.items():
            for path in ("/product-categories", "/units", "/organizations"):
                r = self.c.get(API + path, headers=h)
                self.assertEqual(r.status_code, 200, (u, path, r.text))
                self.assertEqual(r.json()["request_id"], r.headers["X-Request-Id"])
        self.assertEqual(self.c.get(API + "/units").status_code, 401)

    def test_categories_default_active_and_scoped(self):
        h = self.hs["sales"]
        items = self.c.get(API + "/product-categories", params={"page_size": 200}, headers=h).json()["items"]
        codes = {i["code"] for i in items}
        self.assertIn("PIPE_PROFILE", codes)
        self.assertNotIn("LOOKUP_OLD", codes)                                  # default: active only
        self.assertNotIn("BCAT", codes)                                        # other organization never shown
        self.assertTrue(all(i["is_active"] for i in items))
        self.assertEqual(set(items[0]), {"id", "code", "name", "parent_id", "is_active"})
        old = self.c.get(API + "/product-categories", params={"is_active": "false"}, headers=h).json()["items"]
        self.assertIn("LOOKUP_OLD", {i["code"] for i in old})
        self.assertEqual([i["code"] for i in self.c.get(API + "/product-categories", params={"search": "لوله"}, headers=h).json()["items"]], ["PIPE_PROFILE"])
        self.assertEqual([i["code"] for i in self.c.get(API + "/product-categories", headers=self.other).json()["items"]], ["BCAT"])
        self.assertEqual(self.c.get(API + "/product-categories", params={"is_active": "x"}, headers=h).status_code, 422)

    def test_units_filters_and_order(self):
        h = self.hs["accounting"]
        items = self.c.get(API + "/units", params={"page_size": 200}, headers=h).json()["items"]
        codes = [i["code"] for i in items]
        self.assertEqual(codes, sorted(codes))                                 # code ASC
        self.assertIn("KG", codes)
        self.assertNotIn("LOOKUP_OLDU", codes); self.assertNotIn("BKG", codes)
        self.assertEqual(set(items[0]), {"id", "code", "name", "unit_type", "is_active"})
        w = self.c.get(API + "/units", params={"unit_type": "WEIGHT"}, headers=h).json()["items"]
        self.assertTrue(w and all(i["unit_type"] == "WEIGHT" for i in w))
        old = self.c.get(API + "/units", params={"is_active": "false"}, headers=h).json()["items"]
        self.assertIn("LOOKUP_OLDU", {i["code"] for i in old})
        self.assertEqual(self.c.get(API + "/units", params={"unit_type": "KG"}, headers=h).status_code, 422)
        self.assertEqual([i["code"] for i in self.c.get(API + "/units", headers=self.other).json()["items"]], ["BKG"])

    def test_organization(self):
        h = self.hs["admin"]
        r = self.c.get(API + "/organizations", headers=h).json()
        self.assertEqual((r["total"], len(r["items"])), (1, 1))
        org = r["items"][0]
        self.assertEqual(org["code"], "DEMO")
        self.assertEqual(set(org), {"id", "code", "name", "legal_name", "national_id", "economic_code", "registration_number",
                                    "phone", "email", "address", "postal_code", "is_active", "created_at", "updated_at"})
        r = self.c.get(f"{API}/organizations/{org['id']}", headers=h)
        self.assertEqual((r.status_code, r.json()["data"]), (200, org))
        other_id = support.scalar("SELECT id FROM organizations WHERE code = 'OTHER'")
        a = self.c.get(f"{API}/organizations/{other_id}", headers=h)
        b = self.c.get(f"{API}/organizations/{uuid.uuid4()}", headers=h)
        self.assertEqual((a.status_code, err(a)), (404, err(b)))
        self.assertEqual(self.c.get(f"{API}/organizations/xyz", headers=h).status_code, 422)
        self.assertEqual(self.c.get(API + "/organizations", headers=self.other).json()["items"][0]["code"], "OTHER")


if __name__ == "__main__":
    unittest.main()
