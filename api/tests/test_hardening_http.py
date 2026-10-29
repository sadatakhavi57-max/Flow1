"""Reviewer-driven hardening tests: content type, atomic audit, error leakage, unknown/inactive roles, races, search."""
import threading
import unittest
import uuid
from unittest import mock

from fastapi.testclient import TestClient

from tests import support

API = "/api/v1"


def err(r):
    e = dict(r.json()["error"])
    e.pop("request_id")
    return e


@unittest.skipUnless(support.ready(), "SKIPPED: needs PostgreSQL (psql) and TF_SQL_DIR")
class Hardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.build_db()
        cls.app = support.make_app()
        cls.c = TestClient(cls.app)
        cls.admin = support.headers("admin")
        support.scalar("INSERT INTO roles (organization_id, code, name) SELECT id, 'AUDITOR', 'Auditor' FROM organizations WHERE code = 'DEMO' ON CONFLICT DO NOTHING")
        support.scalar("""INSERT INTO users (organization_id, role_id, first_name, last_name, username, password_hash)
                          SELECT u.organization_id, (SELECT r.id FROM roles r WHERE r.code = 'AUDITOR' AND r.organization_id = u.organization_id), 'A', 'B', 'auditor', u.password_hash
                            FROM users u WHERE u.username = 'admin' AND u.organization_id = (SELECT id FROM organizations WHERE code = 'DEMO') ON CONFLICT DO NOTHING""")

    # ------------------------------------------------------------------ content type
    def test_non_json_content_type_is_malformed_request(self):
        body = '{"organization_code": "DEMO", "username": "admin", "password": "x"}'
        for headers in ({"Content-Type": "text/plain"}, {}, {"Content-Type": "application/x-www-form-urlencoded"}):
            r = self.c.post(f"{API}/auth/login", content=body, headers=headers)
            self.assertEqual((r.status_code, err(r)["code"]), (400, "MALFORMED_REQUEST"), headers)
            r = self.c.post(f"{API}/customers", content='{"customer_type":"COMPANY","name":"x"}', headers={**self.admin, **headers})
            self.assertEqual((r.status_code, err(r)["code"]), (400, "MALFORMED_REQUEST"), headers)
        ok = self.c.post(f"{API}/auth/login", content=body.replace('"x"', f'"{support.PASSWORD}"'), headers={"Content-Type": "application/vnd.api+json"})
        self.assertEqual(ok.status_code, 200, ok.text)
        ok = self.c.post(f"{API}/auth/login", content=body.replace('"x"', f'"{support.PASSWORD}"'), headers={"Content-Type": "application/json; charset=utf-8"})
        self.assertEqual(ok.status_code, 200, ok.text)

    def test_wrong_method_and_unknown_route_use_the_envelope(self):
        r = self.c.delete(f"{API}/customers/{uuid.uuid4()}", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], r.json()["error"]["request_id"] == r.headers["X-Request-Id"]), (405, "MALFORMED_REQUEST", True))
        self.assertIn("allow", {k.lower() for k in r.headers})
        r = self.c.get(f"{API}/nope", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (404, "NOT_FOUND"))

    # ------------------------------------------------------------------ audit failure => nothing committed
    def test_failed_audit_rolls_back_the_change(self):
        name = "audit-fail-" + uuid.uuid4().hex[:8]
        with mock.patch("app.customers_service.write_audit", side_effect=RuntimeError("boom")):
            r = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": name}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (500, "INTERNAL_ERROR"))
        self.assertEqual(support.scalar(f"SELECT count(*) FROM customers WHERE name = '{name}'"), "0")
        self.assertEqual(self.c.get(f"{API}/customers", params={"search": name}, headers=self.admin).json()["total"], 0)
        # an update: the stored value must not change either
        ok = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": name}, headers=self.admin).json()["data"]
        with mock.patch("app.customers_service.write_audit", side_effect=RuntimeError("boom")):
            r = self.c.patch(f"{API}/customers/{ok['id']}", json={"name": name + "-2", "updated_at": ok["updated_at"]}, headers=self.admin)
        self.assertEqual(r.status_code, 500)
        self.assertEqual(self.c.get(f"{API}/customers/{ok['id']}", headers=self.admin).json()["data"], ok)

    def test_logout_and_login_are_atomic_with_their_audit(self):
        c = TestClient(support.make_app())
        t = c.post(f"{API}/auth/login", json=support.login_body("accounting")).json()["data"]
        h = {"Authorization": "Bearer " + t["access_token"]}
        with mock.patch("app.auth_service.AuthService._audit", side_effect=RuntimeError("boom")):
            r = c.post(f"{API}/auth/logout", json={"refresh_token": t["refresh_token"]}, headers=h)
            self.assertEqual(r.status_code, 500)
            before = support.scalar("SELECT count(*) FROM refresh_tokens rt JOIN users u ON u.id = rt.user_id WHERE u.username = 'accounting'")
            r = c.post(f"{API}/auth/login", json=support.login_body("accounting"))
            self.assertEqual(r.status_code, 500)
            after = support.scalar("SELECT count(*) FROM refresh_tokens rt JOIN users u ON u.id = rt.user_id WHERE u.username = 'accounting'")
        self.assertEqual(before, after)                                                  # the failed login left no refresh token behind
        r = c.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"]})   # the failed logout did not revoke it
        self.assertEqual(r.status_code, 200, r.text)

    # ------------------------------------------------------------------ nothing internal in error bodies
    def test_internal_errors_leak_nothing(self):
        with mock.patch("app.customers_service.write_audit", side_effect=RuntimeError("secret-internal-detail SELECT * FROM users")):
            r = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": "leak-" + uuid.uuid4().hex[:6]}, headers=self.admin)
        self.assertEqual(r.json()["error"]["message"], "Internal error")
        self.assertEqual(r.json()["error"]["details"], {})
        for bad in ("secret-internal-detail", "SELECT", "Traceback", "RuntimeError", "psycopg", "File \""):
            self.assertNotIn(bad, r.text)
        # a real database error (duplicate) and an unreachable database
        d = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": "n", "national_id": "LEAK" + uuid.uuid4().hex[:6]}, headers=self.admin).json()["data"]
        r = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": "n2", "national_id": d["national_id"]}, headers=self.admin)
        for bad in ("uq_customers", "duplicate key", "INSERT", "violates"):
            self.assertNotIn(bad, r.text)
        from app.main import create_app
        from app.settings import AppSettings
        from tradeflow_core import config as core_config
        down = create_app(AppSettings(core_config.Settings(support.SECRET, 3600, 30, 10, 1, "test"), "host=127.0.0.1 port=1 dbname=x connect_timeout=2", ()))
        r = TestClient(down).post(f"{API}/auth/login", json=support.login_body())
        self.assertEqual((r.status_code, err(r)["code"]), (503, "TEMPORARILY_UNAVAILABLE"))
        for bad in ("127.0.0.1", "connection", "refused", "port"):
            self.assertNotIn(bad, r.text)

    # ------------------------------------------------------------------ unknown / inactive roles
    def test_unknown_role_is_denied_everything_and_inactive_role_is_rejected(self):
        c = TestClient(support.make_app())
        tok = c.post(f"{API}/auth/login", json=support.login_body("auditor"))
        self.assertEqual(tok.status_code, 200, tok.text)
        h = {"Authorization": "Bearer " + tok.json()["data"]["access_token"]}
        for path in ("/customers", "/products", "/purchase-requests", "/units", "/organizations", "/audit-logs"):
            r = c.get(API + path, headers=h)
            self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"), path)
        self.assertEqual(c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": "x"}, headers=h).status_code, 403)
        sales = support.headers("sales")
        support.scalar("UPDATE roles SET is_active = FALSE WHERE code = 'SALES' AND organization_id = (SELECT id FROM organizations WHERE code = 'DEMO')")
        try:
            r = c.get(f"{API}/auth/me", headers=sales)
            self.assertEqual((r.status_code, err(r)["code"]), (401, "AUTH_TOKEN_INVALID"))
            r = c.post(f"{API}/auth/login", json=support.login_body("sales"))
            self.assertEqual((r.status_code, err(r)["code"]), (401, "AUTH_INVALID_CREDENTIALS"))
        finally:
            support.scalar("UPDATE roles SET is_active = TRUE WHERE code = 'SALES' AND organization_id = (SELECT id FROM organizations WHERE code = 'DEMO')")
        self.assertEqual(c.get(f"{API}/auth/me", headers=sales).status_code, 200)

    # ------------------------------------------------------------------ product races
    def _product_body(self, **kw):
        cat = support.scalar("SELECT id FROM product_categories WHERE code = 'PIPE_PROFILE'")
        unit = support.scalar("SELECT id FROM units WHERE code = 'KG' AND organization_id = (SELECT id FROM organizations WHERE code = 'DEMO')")
        return {"code": "R-" + uuid.uuid4().hex[:10], "name": "R-" + uuid.uuid4().hex[:10], "category_id": cat, "default_unit_id": unit, **kw}

    def test_two_stale_product_patches_one_wins(self):
        d = self.c.post(f"{API}/products", json=self._product_body(), headers=self.admin).json()["data"]
        res, bar = [], threading.Barrier(2)

        def go(i):
            c = TestClient(self.app)
            bar.wait()
            res.append(c.patch(f"{API}/products/{d['id']}", json={"description": f"d{i}", "updated_at": d["updated_at"]}, headers=self.admin).status_code)
        ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted(res), [200, 409])

    def test_parallel_product_creation_with_the_same_code(self):
        body = self._product_body()
        res, bar = [], threading.Barrier(6)

        def go(i):
            c = TestClient(self.app)
            bar.wait()
            r = c.post(f"{API}/products", json={**body, "name": f"{body['name']}-{i}"}, headers=self.admin)
            res.append((r.status_code, r.json().get("error", {}).get("code")))
        ts = [threading.Thread(target=go, args=(i,)) for i in range(6)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted(s for s, _ in res), [201] + [409] * 5, res)
        self.assertEqual({c for s, c in res if s == 409}, {"DUPLICATE_RESOURCE"})

    # ------------------------------------------------------------------ search with Persian / Latin digits
    def test_mobile_search_in_both_digit_systems(self):
        tag = uuid.uuid4().int % 10**7
        latin, persian = f"0912{tag:07d}", "".join("۰۱۲۳۴۵۶۷۸۹"[int(ch)] for ch in f"0913{tag:07d}")
        a = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": "m1-" + uuid.uuid4().hex[:6], "mobile": latin}, headers=self.admin).json()["data"]
        b = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": "m2-" + uuid.uuid4().hex[:6], "mobile": persian}, headers=self.admin).json()["data"]
        for term_a, term_b in ((latin, f"0913{tag:07d}"), ("".join("۰۱۲۳۴۵۶۷۸۹"[int(ch)] for ch in latin), persian)):
            ids = [i["id"] for i in self.c.get(f"{API}/customers", params={"search": term_a}, headers=self.admin).json()["items"]]
            self.assertIn(a["id"], ids)
            ids = [i["id"] for i in self.c.get(f"{API}/customers", params={"search": term_b}, headers=self.admin).json()["items"]]
            self.assertIn(b["id"], ids)


if __name__ == "__main__":
    unittest.main()
