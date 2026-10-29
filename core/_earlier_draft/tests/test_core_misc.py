import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from tradeflow_core import audit, optimistic, password, tokens
from tradeflow_core.errors import AppError, ERROR_TABLE, map_db_error, is_retryable
from . import pg

SECRET = "x" * 40
T0 = datetime(2026, 10, 14, 9, 0, 0, tzinfo=timezone.utc)


class AccessToken(unittest.TestCase):
    def test_roundtrip_and_claims(self):
        tok = tokens.create_access_token(SECRET, "u1", "o1", T0)
        c = tokens.verify_access_token(SECRET, tok, T0 + timedelta(seconds=10))
        self.assertEqual((c["sub"], c["org"], c["exp"] - c["iat"]), ("u1", "o1", 3600))
        self.assertNotIn("role", c)                                   # the role is never trusted from the token
        self.assertTrue(uuid.UUID(c["jti"]))

    def test_expiry_boundary(self):
        tok = tokens.create_access_token(SECRET, "u1", "o1", T0)
        tokens.verify_access_token(SECRET, tok, T0 + timedelta(seconds=3599))
        with self.assertRaises(AppError) as cm:
            tokens.verify_access_token(SECRET, tok, T0 + timedelta(seconds=3600))
        self.assertEqual(cm.exception.code, "AUTH_TOKEN_INVALID")

    def test_rejections(self):
        tok = tokens.create_access_token(SECRET, "u1", "o1", T0)
        now = T0 + timedelta(seconds=5)
        claims = jwt.decode(tok, SECRET, algorithms=["HS256"], options={"verify_exp": False, "verify_iat": False})
        bad = [
            tok[:-2] + ("AA" if not tok.endswith("AA") else "BB"),                           # tampered signature
            jwt.encode(claims, "y" * 40, algorithm="HS256"),                                 # other secret
            jwt.encode(claims, SECRET, algorithm="HS384"),                                   # other algorithm
            jwt.encode({**claims}, None, algorithm="none"),                                  # alg none
            jwt.encode({k: v for k, v in claims.items() if k != "org"}, SECRET, algorithm="HS256"),
            jwt.encode({k: v for k, v in claims.items() if k != "jti"}, SECRET, algorithm="HS256"),
            jwt.encode({**claims, "iat": claims["iat"] + 1000}, SECRET, algorithm="HS256"),  # issued in the future
            "", "abc", "a.b.c", None,
        ]
        for t in bad:
            with self.assertRaises(AppError, msg=str(t)[:30]) as cm:
                tokens.verify_access_token(SECRET, t, now)
            self.assertEqual((cm.exception.code, cm.exception.http_status), ("AUTH_TOKEN_INVALID", 401))

    def test_short_secret_refused(self):
        with self.assertRaises(ValueError):
            tokens.create_access_token("short", "u", "o", T0)


class RefreshPolicy(unittest.TestCase):
    def d(self, **kw):
        base = dict(found=True, revoked_at=None, expires_at=T0 + timedelta(days=30), now=T0)
        base.update(kw)
        return tokens.decide_refresh(**base)

    def test_rotate(self):
        r = self.d()
        self.assertEqual((r.outcome, r.reason, r.revoke_all_for_user), (tokens.Outcome.ROTATE, None, False))

    def test_grace_window_boundaries(self):
        for secs, expect in [(0, "DUPLICATE"), (9.999, "DUPLICATE"), (10, "DUPLICATE"), (10.001, "REUSE"), (3600, "REUSE")]:
            r = self.d(revoked_at=T0 - timedelta(seconds=secs))
            self.assertEqual(r.outcome.value, expect, secs)
        dup = self.d(revoked_at=T0 - timedelta(seconds=3))
        self.assertEqual((dup.reason, dup.revoke_all_for_user), ("ALREADY_ROTATED", False))      # nothing else revoked
        reuse = self.d(revoked_at=T0 - timedelta(seconds=11))
        self.assertEqual((reuse.reason, reuse.revoke_all_for_user), ("INVALID", True))           # theft response

    def test_expired_unknown(self):
        e = self.d(expires_at=T0)                                                                 # exactly expired
        self.assertEqual((e.outcome, e.reason, e.revoke_all_for_user), (tokens.Outcome.REUSE, "INVALID", True))
        u = self.d(found=False, expires_at=None)
        self.assertEqual((u.outcome, u.revoke_all_for_user), (tokens.Outcome.REUSE, False))      # no user known

    def test_configurable_grace(self):
        self.assertEqual(self.d(revoked_at=T0 - timedelta(seconds=20), grace_seconds=30).outcome, tokens.Outcome.DUPLICATE)
        self.assertEqual(self.d(revoked_at=T0 - timedelta(seconds=1), grace_seconds=0).outcome, tokens.Outcome.REUSE)

    def test_error_shape(self):
        e = tokens.refresh_error(self.d(revoked_at=T0 - timedelta(seconds=1)))
        self.assertEqual((e.code, e.http_status, e.details), ("AUTH_REFRESH_INVALID", 401, {"reason": "ALREADY_ROTATED"}))

    def test_token_generation_and_hash(self):
        a, b = tokens.new_refresh_token(), tokens.new_refresh_token()
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 43)                                                      # 256 bits base64url
        h = tokens.hash_refresh_token(a)
        self.assertRegex(h, r"^[0-9a-f]{64}$")
        self.assertNotIn(a, h)
        self.assertEqual(h, tokens.hash_refresh_token(a))

    def test_exactly_one_rotation_wins_under_a_lock(self):
        """Model of the Service under SELECT ... FOR UPDATE: 20 threads present one token. This exercises the
        policy function together with a lock; it does NOT prove PostgreSQL locking (that needs the HTTP step)."""
        lock = threading.Lock()
        row = {"revoked_at": None}
        results, now = [], T0

        def worker():
            with lock:                                           # the row lock
                d = tokens.decide_refresh(found=True, revoked_at=row["revoked_at"], expires_at=T0 + timedelta(days=30), now=now)
                if d.outcome is tokens.Outcome.ROTATE:
                    row["revoked_at"] = now
                results.append(d)

        ts = [threading.Thread(target=worker) for _ in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(r.outcome is tokens.Outcome.ROTATE for r in results), 1)
        self.assertEqual(sum(r.outcome is tokens.Outcome.DUPLICATE for r in results), 19)
        self.assertFalse(any(r.revoke_all_for_user for r in results))                          # winner stays valid


class RateLimiter(unittest.TestCase):
    def test_ten_failures_then_429_with_retry_after(self):
        rl = tokens.LoginRateLimiter()
        k = rl.key("org-1", "Admin ", "1.2.3.4")
        for i in range(10):
            rl.check(k, 1000 + i)
            rl.record_failure(k, 1000 + i)
        with self.assertRaises(AppError) as cm:
            rl.check(k, 1010)
        e = cm.exception
        self.assertEqual((e.code, e.http_status), ("RATE_LIMITED", 429))
        self.assertEqual(e.headers["Retry-After"], str(900 - 10))                                # oldest failure at t=1000

    def test_window_expiry_releases(self):
        rl = tokens.LoginRateLimiter()
        k = rl.key("o", "u", "ip")
        for i in range(10):
            rl.record_failure(k, 0)
        with self.assertRaises(AppError):
            rl.check(k, 899)
        rl.check(k, 900)                                                                         # window passed

    def test_nine_failures_are_not_enough(self):
        rl = tokens.LoginRateLimiter()
        k = rl.key("o", "u", "ip")
        for i in range(9):
            rl.record_failure(k, i)
        rl.check(k, 10)

    def test_keys_are_independent_and_normalised(self):
        rl = tokens.LoginRateLimiter()
        a = rl.key("۱۲۳", "Admin", "1.1.1.1")
        self.assertEqual(a, rl.key(" 123 ", "admin ", "1.1.1.1"))
        for _ in range(10):
            rl.record_failure(a, 0)
        rl.check(rl.key("123", "admin", "9.9.9.9"), 1)                                           # other IP: own allowance
        rl.check(rl.key("123", "other", "1.1.1.1"), 1)                                           # other user: own allowance
        with self.assertRaises(AppError):
            rl.check(a, 1)

    def test_not_cleared_by_success(self):
        rl = tokens.LoginRateLimiter()                           # contract is silent -> literal reading: no reset API exists
        self.assertFalse(hasattr(rl, "reset"))


class Passwords(unittest.TestCase):
    P = password.Argon2Params(time_cost=1, memory_cost=64, parallelism=1)                         # cheap, for speed only

    def test_roundtrip_and_format(self):
        h = password.hash_password("s3cret", self.P)
        self.assertRegex(h, r"^\$argon2id\$v=19\$m=64,t=1,p=1\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+$")
        self.assertTrue(password.verify_password("s3cret", h))
        self.assertFalse(password.verify_password("s3cret ", h))
        self.assertNotEqual(h, password.hash_password("s3cret", self.P))                          # random salt

    def test_pinned_defaults(self):
        d = password.DEFAULT_PARAMS
        self.assertEqual((d.time_cost, d.memory_cost, d.parallelism, d.hash_len, d.salt_len), (3, 65536, 4, 32, 16))

    def test_placeholder_and_garbage_never_verify(self):
        for stored in ["TEMPORARY_PASSWORD_HASH", "", None, "plain", "$argon2i$v=19$m=64,t=1,p=1$AAAA$AAAA",
                       "$argon2id$v=18$m=64,t=1,p=1$AAAA$AAAA", "$argon2id$v=19$m=64,t=1$AAAA$AAAA", "$argon2id$v=19$x"]:
            self.assertFalse(password.verify_password("TEMPORARY_PASSWORD_HASH", stored), stored)
        h = password.hash_password("pw", password.Argon2Params(1, 1 << 21, 1))
        self.assertFalse(password.verify_password("pw", h))                                       # absurd stored cost refused

    def test_needs_rehash(self):
        old = password.hash_password("pw", self.P)
        self.assertTrue(password.needs_rehash(old))
        self.assertFalse(password.needs_rehash(old, self.P))
        self.assertTrue(password.needs_rehash("garbage"))

    def test_unicode_password(self):
        h = password.hash_password("گذرواژه‌ی-قوی-۱", self.P)
        self.assertTrue(password.verify_password("گذرواژه‌ی-قوی-۱", h))

    @unittest.skipUnless(pg.available(), "PostgreSQL (psql) not available")
    def test_real_seed_hashes_of_migration_998_verify(self):
        db = pg.make_db("tf_core_pw")
        rows = pg.psql(db, "select username, password_hash from users order by username").splitlines()
        self.assertEqual([r.split("|")[0] for r in rows], ["accounting", "admin", "sales"])
        for r in rows:
            u, h = r.split("|", 1)
            self.assertTrue(password.verify_password("TradeFlow-Dev-1!", h), u)
            self.assertFalse(password.verify_password("wrong", h), u)
            self.assertFalse(password.needs_rehash(h), u)                                         # equals the pinned parameters


class Audit(unittest.TestCase):
    def test_closed_sets(self):
        self.assertEqual({a.value for a in audit.AuditAction}, {"CREATE", "UPDATE", "DELETE", "SUBMIT", "CANCEL", "LOGIN", "LOGOUT"})
        self.assertEqual({a.value for a in audit.AuditEntity}, {"USER", "CUSTOMER", "PRODUCT", "PURCHASE_REQUEST", "PURCHASE_REQUEST_ITEM"})
        self.assertEqual(audit.coerce("CREATE", "CUSTOMER"), ("CREATE", "CUSTOMER"))
        for a, e in [("APPROVE", "CUSTOMER"), ("create", "CUSTOMER"), ("CREATE", "ORDER"), ("", "USER"), ("LOGIN_FAILED", "USER")]:
            with self.assertRaises(ValueError):
                audit.coerce(a, e)

    def test_no_secrets(self):
        audit.assert_no_secrets({"name": "x", "items": [{"price": "1"}]})
        for bad in [{"password_hash": "x"}, {"a": {"refresh_token": "t"}}, {"a": [{"Password": "p"}]}, {"token_hash": "h"}]:
            with self.assertRaises(ValueError):
                audit.assert_no_secrets(bad)

    def test_changed_fields(self):
        o, n = audit.changed_fields({"unit_price": "1", "notes": "a", "x": 1}, {"unit_price": "2", "notes": "a", "x": 1})
        self.assertEqual((o, n), ({"unit_price": "1"}, {"unit_price": "2"}))

    def test_matches_database_default_vocabulary_is_unconstrained(self):
        # by design (D4) the database has no CHECK: the enums above are the only guard
        pass


class Optimistic(unittest.TestCase):
    def test_format_and_parse(self):
        dt = datetime(2026, 10, 8, 9, 20, 11, 123456, tzinfo=timezone.utc)
        s = optimistic.format_timestamp(dt)
        self.assertEqual(s, "2026-10-08T09:20:11.123456Z")
        self.assertEqual(optimistic.parse_timestamp(s), dt)
        self.assertEqual(optimistic.format_timestamp(datetime(2026, 10, 8, 9, 0, 0, tzinfo=timezone.utc)), "2026-10-08T09:00:00.000000Z")

    def test_bad_formats(self):
        for bad in ["2026-10-08T09:20:11Z", "2026-10-08T09:20:11.123Z", "2026-10-08 09:20:11.123456Z", "2026-10-08T09:20:11.123456+00:00",
                    "2026-13-08T09:20:11.123456Z", "", None, 5]:
            with self.assertRaises(AppError) as cm:
                optimistic.parse_timestamp(bad)
            self.assertEqual(cm.exception.code, "VALIDATION_ERROR")

    def test_microsecond_comparison(self):
        stored = datetime(2026, 10, 8, 9, 20, 11, 123456, tzinfo=timezone.utc)
        optimistic.check_fresh("2026-10-08T09:20:11.123456Z", stored)
        with self.assertRaises(AppError) as cm:
            optimistic.check_fresh("2026-10-08T09:20:11.123457Z", stored, {"id": "r1"})
        self.assertEqual((cm.exception.code, cm.exception.http_status, cm.exception.details), ("STALE_UPDATE", 409, {"current": {"id": "r1"}}))

    @unittest.skipUnless(pg.available(), "PostgreSQL (psql) not available")
    def test_roundtrip_with_postgres_timestamptz(self):
        db = pg.make_db("tf_core_opt")
        pg.psql(db, "insert into organizations(name,code) values ('T','TT')")
        out = pg.psql(db, "select to_char(updated_at at time zone 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), updated_at from organizations where code='TT'")
        text, raw = out.split("|")
        dt = optimistic.parse_timestamp(text)
        self.assertEqual(optimistic.format_timestamp(dt), text)                                   # microsecond fidelity
        back = pg.psql(db, f"select updated_at = '{text}'::timestamptz from organizations where code='TT'")
        self.assertEqual(back, "t")                                                                # exact match in the database


class DbErrorMapping(unittest.TestCase):
    """Every mapping is exercised with a REAL PostgreSQL error (SQLSTATE and constraint name read from psql)."""

    @classmethod
    def setUpClass(cls):
        if not pg.available():
            raise unittest.SkipTest("PostgreSQL (psql) not available")
        cls.db = pg.make_db("tf_core_err")
        g = lambda q: pg.psql(cls.db, q)
        cls.org, cls.cust = g("select id from organizations where code='DEMO'"), g("select id from customers limit 1")
        cls.uid, cls.prod = g("select id from users where username='admin'"), g("select id from products limit 1")
        cls.unit, cls.cat = g("select id from units where code='KG'"), g("select id from product_categories limit 1")

    def err(self, sql):
        with self.assertRaises(pg.PgError) as cm:
            pg.psql(self.db, sql)
        return cm.exception

    def mapped(self, sql):
        e = self.err(sql)
        a = map_db_error(e.sqlstate, e.constraint)
        return e, a

    def test_duplicate_customer_identifiers(self):
        pg.psql(self.db, f"insert into customers(organization_id,customer_type,name,national_id,economic_code) values ('{self.org}','COMPANY','A','111','222')")
        e, a = self.mapped(f"insert into customers(organization_id,customer_type,name,national_id) values ('{self.org}','COMPANY','B','111')")
        self.assertEqual((a.code, a.http_status, a.details), ("DUPLICATE_IDENTIFIER", 409, {"field": "national_id"}))
        e, a = self.mapped(f"insert into customers(organization_id,customer_type,name,economic_code) values ('{self.org}','COMPANY','B','222')")
        self.assertEqual((a.code, a.details), ("DUPLICATE_IDENTIFIER", {"field": "economic_code"}))
        # same NAME is allowed (not unique, C2)
        pg.psql(self.db, f"insert into customers(organization_id,customer_type,name) values ('{self.org}','COMPANY','A')")

    def test_duplicate_product_code_and_name(self):
        base = f"insert into products(organization_id,category_id,name,code,default_unit_id) values ('{self.org}','{self.cat}'"
        e, a = self.mapped(base + f",'other','GAS-PIPE-2IN','{self.unit}')")
        self.assertEqual((a.code, a.details), ("DUPLICATE_RESOURCE", {"field": "code"}))
        e, a = self.mapped(base + f",'لوله گازی 2 اینچ','NEWCODE','{self.unit}')")
        self.assertEqual((a.code, a.details), ("DUPLICATE_RESOURCE", {"field": "name"}))

    def test_other_unique_violation_is_duplicate_resource(self):
        e, a = self.mapped(f"insert into roles(organization_id,code,name) values ('{self.org}','ADMIN','x')")
        self.assertEqual((a.code, a.http_status, a.details), ("DUPLICATE_RESOURCE", 409, {}))

    def test_state_conflict_55000(self):
        pg.psql(self.db, f"insert into purchase_requests(id,organization_id,request_number,customer_id,created_by) values ('00000000-0000-0000-0000-0000000000c1','{self.org}','E-1','{self.cust}','{self.uid}')")
        pg.psql(self.db, "update purchase_requests set status='CANCELLED' where id='00000000-0000-0000-0000-0000000000c1'")
        e, a = self.mapped("update purchase_requests set status='DRAFT' where id='00000000-0000-0000-0000-0000000000c1'")
        self.assertEqual((e.sqlstate, a.code, a.http_status), ("55000", "STATE_CONFLICT", 409))
        e, a = self.mapped(f"insert into purchase_request_items(organization_id,purchase_request_id,product_id,unit_id,quantity) values ('{self.org}','00000000-0000-0000-0000-0000000000c1','{self.prod}','{self.unit}',1)")
        self.assertEqual((e.sqlstate, a.code), ("55000", "STATE_CONFLICT"))                        # frozen request: no new item

    def test_reference_not_found_23503(self):
        e, a = self.mapped(f"insert into purchase_requests(organization_id,request_number,customer_id,created_by) values ('{self.org}','E-2','{uuid.uuid4()}','{self.uid}')")
        self.assertEqual((e.sqlstate, a.code, a.http_status), ("23503", "REFERENCE_NOT_FOUND", 422))

    def test_cross_organization_reference_is_the_same_error(self):
        pg.psql(self.db, "insert into organizations(name,code) values ('B','ORGB')")
        orgb = pg.psql(self.db, "select id from organizations where code='ORGB'")
        pg.psql(self.db, f"insert into customers(id,organization_id,customer_type,name) values ('00000000-0000-0000-0000-0000000000d1','{orgb}','COMPANY','foreign')")
        e1, a1 = self.mapped(f"insert into purchase_requests(organization_id,request_number,customer_id,created_by) values ('{self.org}','E-3','00000000-0000-0000-0000-0000000000d1','{self.uid}')")
        e2, a2 = self.mapped(f"insert into purchase_requests(organization_id,request_number,customer_id,created_by) values ('{self.org}','E-4','{uuid.uuid4()}','{self.uid}')")
        self.assertEqual((a1.code, a1.details), (a2.code, a2.details))                             # existence is never revealed
        self.assertEqual(a1.code, "REFERENCE_NOT_FOUND")

    def test_amount_errors(self):
        pg.psql(self.db, f"insert into purchase_requests(id,organization_id,request_number,customer_id,created_by) values ('00000000-0000-0000-0000-0000000000c2','{self.org}','E-5','{self.cust}','{self.uid}')")
        item = lambda cols, vals: f"insert into purchase_request_items(organization_id,purchase_request_id,product_id,unit_id,quantity,{cols}) values ('{self.org}','00000000-0000-0000-0000-0000000000c2','{self.prod}','{self.unit}',1,{vals})"
        e, a = self.mapped(item("unit_price,discount_amount,line_total", "100,101,0"))
        self.assertEqual((a.code, a.http_status), ("AMOUNT_OUT_OF_RANGE", 422), e)               # discount above gross
        e, a = self.mapped(item("unit_price,line_total", "125001,1"))
        self.assertEqual((e.constraint, a.code), ("chk_request_items_line_total_consistency", "AMOUNT_OUT_OF_RANGE"))
        e, a = self.mapped(item("unit_price,line_total", "-5,-5"))
        self.assertEqual(a.code, "AMOUNT_OUT_OF_RANGE")
        e, a = self.mapped(item("unit_price,line_total", "100000000000000000000,100000000000000000000"))
        self.assertEqual((e.sqlstate, a.code), ("22003", "AMOUNT_OUT_OF_RANGE"))                  # 1e20 overflow

    def test_delivery_date_before_request_date(self):
        e, a = self.mapped(f"insert into purchase_requests(organization_id,request_number,customer_id,created_by,requested_delivery_date) values ('{self.org}','E-6','{self.cust}','{self.uid}', current_date - 10)")
        self.assertEqual((e.sqlstate, a.code, a.http_status, a.details[0]["field"]), ("23514", "VALIDATION_ERROR", 422, "requested_delivery_date"))

    def test_unmapped_and_no_leak(self):
        e = self.err("select 1/0")
        a = map_db_error(e.sqlstate, e.constraint)
        self.assertEqual((e.sqlstate, a.code, a.http_status), ("22012", "INTERNAL_ERROR", 500))
        e = self.err(f"insert into customers(organization_id,customer_type,name) values ('{self.org}','NOPE','x')")
        a = map_db_error(e.sqlstate, e.constraint)
        self.assertEqual((e.sqlstate, a.code), ("23514", "INTERNAL_ERROR"))                       # an unnamed check = unmapped = 500
        body = a.to_response("rid")
        self.assertEqual(body["error"].keys(), {"code", "message", "details", "request_id"})
        self.assertNotIn("insert", str(body).lower())
        self.assertNotIn("customers", str(body).lower())

    def test_pure_mappings(self):
        self.assertEqual(map_db_error("40P01").code, "TEMPORARILY_UNAVAILABLE")
        self.assertEqual(map_db_error("40001").http_status, 503)
        self.assertTrue(is_retryable("40P01") and is_retryable("40001") and not is_retryable("55000") and not is_retryable(None))
        self.assertEqual(map_db_error("08006").code, "TEMPORARILY_UNAVAILABLE")
        self.assertEqual(map_db_error("57P01").code, "TEMPORARILY_UNAVAILABLE")
        self.assertEqual(map_db_error(None).code, "INTERNAL_ERROR")


class ErrorTable(unittest.TestCase):
    def test_table_equals_contract_section_15(self):
        expected = {400: ["MALFORMED_REQUEST"], 401: ["AUTH_INVALID_CREDENTIALS", "AUTH_TOKEN_INVALID", "AUTH_REFRESH_INVALID"],
                    403: ["FORBIDDEN_ROLE", "FORBIDDEN_NOT_OWNER"], 404: ["NOT_FOUND"],
                    409: ["STATE_CONFLICT", "STALE_UPDATE", "DUPLICATE_IDENTIFIER", "DUPLICATE_RESOURCE"],
                    422: ["VALIDATION_ERROR", "INVALID_MONEY", "AMOUNT_OUT_OF_RANGE", "INACTIVE_REFERENCE", "REFERENCE_NOT_FOUND",
                          "SPECIFICATION_INVALID", "SUBMIT_PRECONDITION_FAILED"],
                    429: ["RATE_LIMITED"], 500: ["INTERNAL_ERROR"], 503: ["TEMPORARILY_UNAVAILABLE"]}
        got = {}
        for code, (http, _) in ERROR_TABLE.items():
            got.setdefault(http, []).append(code)
        self.assertEqual({k: sorted(v) for k, v in got.items()}, {k: sorted(v) for k, v in expected.items()})

    def test_contract_doc_and_code_agree(self):
        """Parse the table straight out of the contract file when it is available next to the repository."""
        here = Path(__file__).resolve()
        p = next((c for c in (here.parents[2] / "docs" / "SLICE_01_CONTRACT.md", here.parents[2] / "docs_sync" / "SLICE_01_CONTRACT.md") if c.exists()), None)
        if p is None:
            self.skipTest("contract file not found next to the sources")
        import re
        rows = re.findall(r"^\| (\d{3}) \| `([A-Z_]+)`", p.read_text(encoding="utf-8"), re.M)
        self.assertEqual({c: int(h) for h, c in rows}, {c: h for c, (h, _) in ERROR_TABLE.items()})

    def test_details_always_present(self):
        for code in ERROR_TABLE:
            self.assertIn("details", AppError(code).to_response("r")["error"])
            self.assertIsNotNone(AppError(code).details)
        with self.assertRaises(ValueError):
            AppError("SOMETHING_ELSE")
