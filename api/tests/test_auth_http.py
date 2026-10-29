import threading
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests import pg, support
from tradeflow_core.ratelimit import LoginRateLimiter

A = "/api/v1/auth"


@unittest.skipUnless(support.ready(), "SKIPPED: needs PostgreSQL (psql) and TF_SQL_DIR")
class AuthHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.build_db()

    def setUp(self):
        self.app = support.make_app()
        self.c = TestClient(self.app)
        # a clean slate for tokens and users the tests may have changed
        pg.psql(support.DB, "DELETE FROM refresh_tokens; UPDATE users SET is_active = TRUE")

    def login(self, user="admin", **kw):
        r = self.c.post(f"{A}/login", json=support.login_body(user, **kw))
        return r

    def tokens(self, user="admin"):
        r = self.login(user)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]

    def hdr(self, t):
        return {"Authorization": f"Bearer {t['access_token']}"}

    # ------------------------------------------------------------------ login / me
    def test_login_shape_and_request_id(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["request_id"], r.headers["X-Request-Id"])
        u = d["data"]
        self.assertEqual((u["token_type"], u["expires_in"]), ("bearer", 3600))
        self.assertEqual(u["user"]["username"], "admin")
        self.assertEqual(u["user"]["role"]["code"], "ADMIN")
        self.assertEqual(u["user"]["organization"]["code"], "DEMO")
        self.assertNotIn("password_hash", r.text)

    def test_login_normalizes_org_and_username(self):
        r = self.c.post(f"{A}/login", json={"organization_code": " demo ", "username": " ADMIN ", "password": support.PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)

    def test_all_login_failures_are_identical(self):
        bodies = [support.login_body(password="wrong"), support.login_body(user="nobody"), support.login_body(org="NOPE")]
        pg.psql(support.DB, "UPDATE users SET is_active = FALSE WHERE username = 'sales'")
        bodies.append(support.login_body(user="sales"))
        seen = set()
        for b in bodies:
            r = self.c.post(f"{A}/login", json=b)
            self.assertEqual(r.status_code, 401)
            e = r.json()["error"]
            seen.add((e["code"], e["message"], str(e["details"])))
        self.assertEqual(len(seen), 1, seen)
        self.assertEqual(next(iter(seen))[0], "AUTH_INVALID_CREDENTIALS")

    def test_bad_login_bodies(self):
        r = self.c.post(f"{A}/login", json={"organization_code": "DEMO", "username": "a", "password": "x", "role": "ADMIN"})
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (422, "VALIDATION_ERROR"))
        r = self.c.post(f"{A}/login", content=b"{not json", headers={"Content-Type": "application/json"})
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (400, "MALFORMED_REQUEST"))
        self.assertEqual(r.json()["error"]["request_id"], r.headers["X-Request-Id"])

    def test_rate_limit_after_ten_failures(self):
        for _ in range(10):
            self.assertEqual(self.login(password="bad").status_code, 401)
        r = self.login(password="bad")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (429, "RATE_LIMITED"))
        self.assertGreaterEqual(int(r.headers["Retry-After"]), 1)
        self.assertEqual(self.login(user="sales").status_code, 200)          # another key keeps its own allowance

    def test_me_and_token_rejections(self):
        t = self.tokens()
        r = self.c.get(f"{A}/me", headers=self.hdr(t))
        self.assertEqual((r.status_code, r.json()["data"]["username"]), (200, "admin"))
        for h in ({}, {"Authorization": "Bearer garbage"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}):
            r = self.c.get(f"{A}/me", headers=h)
            self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "AUTH_TOKEN_INVALID"))

    def test_expired_token_rejected(self):
        t0 = datetime.now(timezone.utc) - timedelta(hours=2)
        c = TestClient(support.make_app(clock=lambda: t0))
        tok = c.post(f"{A}/login", json=support.login_body()).json()["data"]
        r = self.c.get(f"{A}/me", headers=self.hdr(tok))
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "AUTH_TOKEN_INVALID"))

    def test_deactivated_user_rejected_immediately(self):
        t = self.tokens("sales")
        pg.psql(support.DB, "UPDATE users SET is_active = FALSE WHERE username = 'sales'")
        r = self.c.get(f"{A}/me", headers=self.hdr(t))
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "AUTH_TOKEN_INVALID"))

    # ------------------------------------------------------------------ refresh
    def test_refresh_rotates_and_duplicate_is_benign(self):
        t = self.tokens()
        r1 = self.c.post(f"{A}/refresh", json={"refresh_token": t["refresh_token"]})
        self.assertEqual(r1.status_code, 200, r1.text)
        new = r1.json()["data"]
        self.assertNotEqual(new["refresh_token"], t["refresh_token"])
        r2 = self.c.post(f"{A}/refresh", json={"refresh_token": t["refresh_token"]})
        self.assertEqual((r2.status_code, r2.json()["error"]["code"], r2.json()["error"]["details"]["reason"]),
                         (401, "AUTH_REFRESH_INVALID", "ALREADY_ROTATED"))
        r3 = self.c.post(f"{A}/refresh", json={"refresh_token": new["refresh_token"]})      # the winner's token still works
        self.assertEqual(r3.status_code, 200, r3.text)

    def test_reuse_after_grace_revokes_everything(self):
        t = self.tokens()
        new = self.c.post(f"{A}/refresh", json={"refresh_token": t["refresh_token"]}).json()["data"]
        pg.psql(support.DB, "UPDATE refresh_tokens SET revoked_at = NOW() - interval '30 seconds' WHERE revoked_at IS NOT NULL")
        r = self.c.post(f"{A}/refresh", json={"refresh_token": t["refresh_token"]})
        self.assertEqual((r.status_code, r.json()["error"]["details"]["reason"]), (401, "INVALID"))
        r = self.c.post(f"{A}/refresh", json={"refresh_token": new["refresh_token"]})       # theft response: the new one is dead too
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "AUTH_REFRESH_INVALID"))

    def test_unknown_refresh_token(self):
        r = self.c.post(f"{A}/refresh", json={"refresh_token": "nope"})
        self.assertEqual((r.status_code, r.json()["error"]["details"]["reason"]), (401, "INVALID"))

    def test_concurrent_refresh_exactly_one_winner(self):
        """Real PostgreSQL SELECT ... FOR UPDATE: 8 simultaneous refreshes with ONE token."""
        t = self.tokens()
        results, barrier = [], threading.Barrier(8)

        def worker():
            c = TestClient(self.app)
            barrier.wait()
            r = c.post(f"{A}/refresh", json={"refresh_token": t["refresh_token"]})
            results.append((r.status_code, r.json()))
        ths = [threading.Thread(target=worker) for _ in range(8)]
        [x.start() for x in ths]; [x.join() for x in ths]
        wins = [j for s, j in results if s == 200]
        dups = [j for s, j in results if s == 401 and j["error"]["details"].get("reason") == "ALREADY_ROTATED"]
        self.assertEqual((len(wins), len(dups)), (1, 7), results)
        r = self.c.post(f"{A}/refresh", json={"refresh_token": wins[0]["data"]["refresh_token"]})
        self.assertEqual(r.status_code, 200, "the winner's token must still be valid after the race")
        rc, out, _ = pg.psql(support.DB, "SELECT count(*) FILTER (WHERE revoked_at IS NULL) FROM refresh_tokens")
        self.assertEqual(out.strip(), "1")

    # ------------------------------------------------------------------ logout / audit
    def test_logout_204_and_header(self):
        t = self.tokens()
        r = self.c.post(f"{A}/logout", json={"refresh_token": t["refresh_token"]}, headers=self.hdr(t))
        self.assertEqual((r.status_code, r.content), (204, b""))
        self.assertTrue(r.headers["X-Request-Id"])
        r = self.c.post(f"{A}/refresh", json={"refresh_token": t["refresh_token"]})
        self.assertEqual(r.status_code, 401)

    def test_logout_cannot_revoke_someone_elses_token(self):
        admin, sales = self.tokens("admin"), self.tokens("sales")
        r = self.c.post(f"{A}/logout", json={"refresh_token": sales["refresh_token"]}, headers=self.hdr(admin))
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "AUTH_REFRESH_INVALID"))
        self.assertEqual(self.c.post(f"{A}/refresh", json={"refresh_token": sales["refresh_token"]}).status_code, 200)
        r = self.c.post(f"{A}/logout", json={"refresh_token": admin["refresh_token"]})      # no access token
        self.assertEqual(r.status_code, 401)

    def test_audit_rows_without_secrets(self):
        count = lambda: int(pg.psql(support.DB, "SELECT count(*) FROM audit_logs WHERE action IN ('LOGIN','LOGOUT')")[1].strip())
        before = count()                                                                     # audit_logs is append-only: compare deltas
        t = self.tokens()
        self.c.post(f"{A}/logout", json={"refresh_token": t["refresh_token"]}, headers=self.hdr(t))
        self.login(password="bad")                                                           # D4: failed logins are not audited
        self.assertEqual(count() - before, 2)
        rc, out, e = pg.psql(support.DB, "SELECT action, entity_type, coalesce(new_data::text,''), coalesce(old_data::text,'') FROM (SELECT * FROM audit_logs WHERE action IN ('LOGIN','LOGOUT') ORDER BY created_at DESC, id DESC LIMIT 2) x ORDER BY action")
        self.assertEqual(rc, 0, e)
        self.assertEqual([l.split("|")[0] for l in out.strip().splitlines()], ["LOGIN", "LOGOUT"])
        for bad in ("token", "password", "TradeFlow"):
            self.assertNotIn(bad, out)

    def test_unknown_route_and_method_use_the_envelope(self):
        r = self.c.get("/api/v1/nothing")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (404, "NOT_FOUND"))
        self.assertEqual(r.json()["error"]["request_id"], r.headers["X-Request-Id"])


if __name__ == "__main__":
    unittest.main()
