import base64
import json
import os
import re
import threading
import unittest
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from tradeflow_core import passwords as pw, tokens as tk
from tradeflow_core.errors import AppError, ErrorCode
from tradeflow_core.ratelimit import LoginRateLimiter, normalize_key

SECRET = "s" * 40
UID, OID = str(uuid.uuid4()), str(uuid.uuid4())
T0 = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
FAST = pw.Argon2Params(time_cost=1, memory_cost=64, parallelism=1)           # tests only; production params are DEFAULT_PARAMS


def code_of(fn, *a, **k):
    try:
        fn(*a, **k)
    except AppError as e:
        return e.code, e.details
    return None, None


class AccessToken(unittest.TestCase):
    def test_roundtrip_and_claims(self):
        tok, claims = tk.issue_access_token(SECRET, UID, OID, T0)
        c = tk.verify_access_token(SECRET, tok, T0 + timedelta(seconds=10))
        self.assertEqual((c["sub"], c["org"], c["exp"] - c["iat"]), (UID, OID, 3600))
        self.assertEqual(set(c), {"sub", "org", "iat", "exp", "jti"})            # no role in the token
        self.assertNotEqual(tk.issue_access_token(SECRET, UID, OID, T0)[1]["jti"], claims["jti"])

    def test_expiry_boundary(self):
        tok, _ = tk.issue_access_token(SECRET, UID, OID, T0)
        tk.verify_access_token(SECRET, tok, T0 + timedelta(seconds=3599))
        self.assertEqual(code_of(tk.verify_access_token, SECRET, tok, T0 + timedelta(seconds=3600))[0], ErrorCode.AUTH_TOKEN_INVALID)

    def test_every_failure_is_the_same_error(self):
        tok, _ = tk.issue_access_token(SECRET, UID, OID, T0)
        good = jwt.decode(tok, SECRET, algorithms=["HS256"], options={"verify_exp": False})
        warnings.simplefilter("ignore")                                                   # PyJWT key-length advisory for HS384 sample
        forged = [
            jwt.encode(good, "x" * 40, algorithm="HS256"),                               # wrong secret
            jwt.encode(good, SECRET, algorithm="HS384"),                                 # other HMAC alg
            jwt.encode(good, None, algorithm="none"),                                    # alg none
            tok[:-3] + ("AAA" if not tok.endswith("AAA") else "BBB"),                    # tampered signature
            jwt.encode({k: v for k, v in good.items() if k != "org"}, SECRET, algorithm="HS256"),
            jwt.encode({k: v for k, v in good.items() if k != "jti"}, SECRET, algorithm="HS256"),
            jwt.encode({**good, "sub": "not-a-uuid"}, SECRET, algorithm="HS256"),
            jwt.encode({**good, "exp": good["iat"] + 86400}, SECRET, algorithm="HS256"),  # lifetime above 1 h
            "", "abc", "a.b.c", None, 5,
        ]
        for f in forged:
            self.assertEqual(code_of(tk.verify_access_token, SECRET, f, T0)[0], ErrorCode.AUTH_TOKEN_INVALID, f)

    def test_secret_must_be_long(self):
        with self.assertRaises(ValueError): tk.issue_access_token("short", UID, OID, T0)
        with self.assertRaises(ValueError): tk.verify_access_token("short", "x", T0)


class Decision(unittest.TestCase):
    def row(self, revoked=None, exp=T0 + timedelta(days=30)):
        return tk.RefreshRow("r", UID, OID, "h", exp, revoked)

    def test_decision_table(self):
        D = tk.Decision
        self.assertEqual(tk.decide_refresh(None, T0), (D.INVALID, False))
        self.assertEqual(tk.decide_refresh(self.row(), T0), (D.ROTATE, False))
        self.assertEqual(tk.decide_refresh(self.row(revoked=T0 - timedelta(seconds=1)), T0), (D.ALREADY_ROTATED, False))
        self.assertEqual(tk.decide_refresh(self.row(revoked=T0 - timedelta(seconds=10)), T0), (D.ALREADY_ROTATED, False))   # <= 10 s
        self.assertEqual(tk.decide_refresh(self.row(revoked=T0 - timedelta(seconds=10, microseconds=1)), T0), (D.INVALID, True))
        self.assertEqual(tk.decide_refresh(self.row(exp=T0), T0), (D.INVALID, True))                   # expired exactly now
        self.assertEqual(tk.decide_refresh(self.row(exp=T0 + timedelta(microseconds=1)), T0), (D.ROTATE, False))
        # revoked AND expired, within the grace window: benign duplicate wins (order of the contract)
        self.assertEqual(tk.decide_refresh(self.row(revoked=T0 - timedelta(seconds=2), exp=T0 - timedelta(days=1)), T0),
                         (D.ALREADY_ROTATED, False))
        self.assertEqual(tk.decide_refresh(self.row(revoked=T0 - timedelta(seconds=5)), T0, grace_seconds=3), (D.INVALID, True))


class Clock:
    def __init__(self): self.t = T0
    def __call__(self): return self.t
    def advance(self, s): self.t += timedelta(seconds=s)


class RefreshFlow(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.store = tk.InMemoryStore()
        self.svc = tk.RefreshService(self.store, now=self.clock)

    def active(self, user=UID):
        return [r for r in self.store.rows.values() if r.user_id == user and r.revoked_at is None]

    def test_rotation(self):
        a = self.svc.login_issue(UID, OID)
        self.assertNotIn(a.raw, [r.token_hash for r in self.store.rows.values()])         # only the hash is stored
        self.assertEqual(len(a.row.token_hash), 64)
        self.assertEqual(a.row.expires_at, T0 + timedelta(days=30))
        b = self.svc.refresh(a.raw)
        self.assertNotEqual(a.raw, b.raw)
        self.assertEqual([r.id for r in self.active()], [b.row.id])

    def test_duplicate_within_grace_is_benign_and_keeps_the_winner_valid(self):
        a = self.svc.login_issue(UID, OID)
        other = self.svc.login_issue(UID, OID)                                              # a second session of the same user
        b = self.svc.refresh(a.raw)
        self.clock.advance(3)
        c, d = code_of(self.svc.refresh, a.raw)
        self.assertEqual((c, d), (ErrorCode.AUTH_REFRESH_INVALID, {"reason": "ALREADY_ROTATED"}))
        self.assertEqual({r.id for r in self.active()}, {b.row.id, other.row.id})           # nothing extra revoked
        self.svc.refresh(b.raw)                                                             # winner's token still works

    def test_real_reuse_after_grace_revokes_everything_of_the_user_and_commits(self):
        a = self.svc.login_issue(UID, OID); other = self.svc.login_issue(UID, OID)
        victim = self.svc.login_issue(str(uuid.uuid4()), OID)                               # another user, must be untouched
        b = self.svc.refresh(a.raw)
        self.clock.advance(11)
        self.assertEqual(code_of(self.svc.refresh, a.raw), (ErrorCode.AUTH_REFRESH_INVALID, {"reason": "INVALID"}))
        self.assertEqual(self.active(), [])                                                 # revocation survived the raised error
        self.assertEqual(len(self.active(victim.row.user_id)), 1)
        self.assertEqual(code_of(self.svc.refresh, b.raw)[0], ErrorCode.AUTH_REFRESH_INVALID)

    def test_expired_and_unknown_tokens(self):
        a = self.svc.login_issue(UID, OID); keep = self.svc.login_issue(UID, OID)
        self.assertEqual(code_of(self.svc.refresh, "nonsense"), (ErrorCode.AUTH_REFRESH_INVALID, {"reason": "INVALID"}))
        self.assertEqual(len(self.active()), 2)                                             # unknown token revokes nobody
        self.clock.advance(30 * 86400)
        self.assertEqual(code_of(self.svc.refresh, a.raw)[1], {"reason": "INVALID"})
        for bad in [None, "", 5]:
            self.assertEqual(code_of(self.svc.refresh, bad)[0], ErrorCode.AUTH_REFRESH_INVALID)

    def test_race_20_parallel_refreshes_of_one_token(self):                                 # T-REFRESH (policy level)
        for round_ in range(25):
            store = tk.InMemoryStore(); clock = Clock(); svc = tk.RefreshService(store, now=clock)
            a = svc.login_issue(UID, OID); out = []; barrier = threading.Barrier(20)

            def go():
                barrier.wait()
                try:
                    out.append(("ok", svc.refresh(a.raw)))
                except AppError as e:
                    out.append((e.details["reason"], None))
            ts = [threading.Thread(target=go) for _ in range(20)]
            [t.start() for t in ts]; [t.join() for t in ts]
            self.assertEqual(sorted(k for k, _ in out), ["ALREADY_ROTATED"] * 19 + ["ok"], round_)
            winner = next(v for k, v in out if k == "ok")
            active = [r for r in store.rows.values() if r.revoked_at is None]
            self.assertEqual([r.id for r in active], [winner.row.id])                       # the winner's token survived the race
            svc.refresh(winner.raw)                                                         # and is usable

    def test_logout_rules(self):
        a = self.svc.login_issue(UID, OID)
        stranger = self.svc.login_issue(str(uuid.uuid4()), OID)
        foreign_org = self.svc.login_issue(UID, str(uuid.uuid4()))
        for raw in [stranger.raw, foreign_org.raw, "nonsense", None]:
            self.assertEqual(code_of(self.svc.logout, raw, UID, OID)[0], ErrorCode.AUTH_REFRESH_INVALID)
        self.assertIsNone(stranger.row.revoked_at)
        self.assertEqual(len([r for r in self.store.rows.values() if r.revoked_at]), 0)    # nothing was revoked by the failed calls
        self.svc.logout(a.raw, UID, OID)
        self.assertEqual(code_of(self.svc.refresh, a.raw)[0], ErrorCode.AUTH_REFRESH_INVALID)
        self.svc.logout(a.raw, UID, OID)                                                    # idempotent for the caller's own token
        self.assertEqual(len(self.active(stranger.row.user_id)), 1)


class Passwords(unittest.TestCase):
    def test_rfc9106_argon2id_known_answer(self):
        """RFC 9106 section 5.3 test vector: proves the KDF primitive is Argon2id, not just 'something'."""
        k = Argon2id(salt=bytes([2]) * 16, length=32, iterations=3, lanes=4, memory_cost=32,
                     secret=bytes([3]) * 8, ad=bytes([4]) * 12).derive(bytes([1]) * 32)
        self.assertEqual(k.hex(), "0d640df58d78766c08c037a34a8b53c9d01ef0452d75b65eb52520e96b01e659")

    def test_hash_verify_and_phc_layout(self):
        h = pw.hash_password("correct horse", FAST)
        self.assertRegex(h, r"^\$argon2id\$v=19\$m=64,t=1,p=1\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}$")   # 16-byte salt, 32-byte hash, no padding
        self.assertTrue(pw.verify_password("correct horse", h))
        self.assertFalse(pw.verify_password("correct horsE", h))
        self.assertNotEqual(h, pw.hash_password("correct horse", FAST))                        # random salt

    def test_default_parameters_are_the_contract_values(self):
        p = pw.DEFAULT_PARAMS
        self.assertEqual((p.time_cost, p.memory_cost, p.parallelism, p.hash_len, p.salt_len), (3, 65536, 4, 32, 16))

    def test_garbage_never_verifies_and_never_raises(self):
        for bad in ["TEMPORARY_PASSWORD_HASH", "", None, "$argon2id$v=19$m=65536,t=3,p=4$x$y", "$argon2i$v=19$m=64,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA",
                    "$argon2id$v=19$m=99999999,t=1,p=1$c2FsdHNhbHRzYWx0$" + "A" * 43,          # absurd memory: refused, not computed
                    "$argon2id$v=19$m=64,t=999,p=1$c2FsdHNhbHRzYWx0$" + "A" * 43]:
            self.assertFalse(pw.verify_password("anything", bad), bad)
        h = pw.hash_password("x", FAST)
        for badpw in ["", None, 5, "y" * 2000]:
            self.assertFalse(pw.verify_password(badpw, h))
        with self.assertRaises(ValueError): pw.hash_password("")

    def test_needs_rehash(self):
        self.assertTrue(pw.needs_rehash(pw.hash_password("x", FAST)))                         # older/cheaper parameters
        self.assertFalse(pw.needs_rehash(pw.hash_password("x", FAST), FAST))
        self.assertTrue(pw.needs_rehash("TEMPORARY_PASSWORD_HASH"))

    def test_dummy_verification_for_unknown_user(self):
        self.assertFalse(pw.verify_or_dummy("whatever", None))
        self.assertTrue(pw.verify_or_dummy("x", pw.hash_password("x", FAST)))

    def test_seed_998_hashes_verify_with_the_documented_dev_password(self):
        cands = [Path(os.environ["TF_SQL_DIR"]) / "998_dev_seed_auth.sql"] if os.environ.get("TF_SQL_DIR") else []
        if not cands or not cands[0].is_file():
            self.skipTest("SKIPPED: TF_SQL_DIR not set")
        hashes = re.findall(r"'(\$argon2id\$[^']+)'", cands[0].read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(set(hashes)), 3)
        for h in set(hashes):
            self.assertTrue(pw.verify_password("TradeFlow-Dev-1!", h))
            self.assertFalse(pw.needs_rehash(h))                                              # equal to the contract parameters


class RateLimit(unittest.TestCase):
    def setUp(self):
        self.t = [0.0]; self.rl = LoginRateLimiter(clock=lambda: self.t[0]); self.k = normalize_key("org-1", "Admin", "1.2.3.4")

    def fail(self, n, key=None):
        for _ in range(n): self.rl.record_failure(key or self.k)

    def test_ten_failures_then_429_with_retry_after(self):
        self.fail(9); self.rl.check(self.k)                                                  # 9 failures: still allowed
        self.fail(1)
        c, d = code_of(self.rl.check, self.k)
        self.assertEqual((c, d), (ErrorCode.RATE_LIMITED, {"retry_after": 900}))
        self.t[0] = 600
        self.assertEqual(code_of(self.rl.check, self.k)[1], {"retry_after": 300})
        self.t[0] = 899.5
        self.assertEqual(code_of(self.rl.check, self.k)[1], {"retry_after": 1})
        self.t[0] = 900.0
        self.rl.check(self.k)                                                                # the window has passed

    def test_window_slides(self):
        for i in range(10):
            self.t[0] = i * 10; self.rl.record_failure(self.k)                               # failures at 0,10,...,90
        self.t[0] = 899; self.assertEqual(code_of(self.rl.check, self.k)[0], ErrorCode.RATE_LIMITED)
        self.t[0] = 901; self.rl.check(self.k)                                               # the failure at t=0 aged out -> 9 left

    def test_keys_are_independent_and_normalized(self):
        self.fail(10)
        self.rl.check(normalize_key("ORG-1", "admin", "9.9.9.9"))                            # other IP: its own allowance
        self.rl.check(normalize_key("ORG-1", "sales", "1.2.3.4"))
        self.assertEqual(code_of(self.rl.check, normalize_key(" org-1 ", " ADMIN ", "1.2.3.4"))[0], ErrorCode.RATE_LIMITED)
        self.assertEqual(normalize_key("ORG-۱", "A", "ip"), ("ORG-1", "a", "ip"))

    def test_memory_is_bounded(self):
        rl = LoginRateLimiter(max_keys=100, clock=lambda: 0.0)
        for i in range(1000): rl.record_failure(("o", f"u{i}", "ip"))
        self.assertLessEqual(len(rl._events), 100)

    def test_thread_safety(self):
        rl = LoginRateLimiter(max_failures=10 ** 9); k = ("o", "u", "ip")
        ts = [threading.Thread(target=lambda: [rl.record_failure(k) for _ in range(500)]) for _ in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(rl._events[k]), 4000)


if __name__ == "__main__":
    unittest.main()
