import random
import unittest
from decimal import Decimal as D, ROUND_HALF_EVEN

from tradeflow_core import money as m
from tradeflow_core.errors import AppError, ErrorCode
from . import pg


def err(fn, *a):
    try:
        fn(*a)
    except AppError as e:
        return e
    raise AssertionError("no AppError raised")


class Parse(unittest.TestCase):
    def test_money_valid(self):
        for s, want in [("0", 0), ("125000", 125000), ("۱۲۵۰۰۰", 125000), (" 7 ", 7), ("9" * 20, 10**20 - 1)]:
            self.assertEqual(m.parse_money(s), D(want))

    def test_money_invalid_all_INVALID_MONEY(self):
        for bad in ["125000.00", "1.5", "-1", "", "abc", "007", "1e3", "1,000", "9" * 21, 125000, 1.5, None, True, [], {}]:
            self.assertEqual(err(m.parse_money, bad).code, ErrorCode.INVALID_MONEY, repr(bad))

    def test_quantity(self):
        self.assertEqual(m.parse_quantity("10.000"), D("10.000"))
        self.assertEqual(m.parse_quantity("۱۰٫۵".replace("٫", ".")), D("10.5"))
        self.assertEqual(m.parse_quantity("1" * 15 + ".123"), D("1" * 15 + ".123"))
        for bad in ["1" * 16, "1.1234", "-1", ".5", "1.", "1,5", 5, 5.0]:
            self.assertEqual(err(m.parse_quantity, bad).code, ErrorCode.INVALID_MONEY, repr(bad))
        for zero in ["0", "0.000"]:
            self.assertEqual(err(m.parse_quantity, zero).code, ErrorCode.VALIDATION_ERROR)

    def test_weight(self):
        self.assertIsNone(m.parse_estimated_weight(None))
        self.assertEqual(m.parse_estimated_weight("0"), D(0))
        self.assertEqual(err(m.parse_estimated_weight, "-1").code, ErrorCode.INVALID_MONEY)

    def test_bundle_count_cap_is_18_digits_and_never_INVALID_MONEY(self):   # T-CAP
        self.assertEqual(m.parse_bundle_count("9" * 18), D("9" * 18))
        self.assertEqual(m.parse_bundle_count("0"), D(0))
        for bad in ["9" * 19, "1.5", "-1", "01", "", 3, None]:
            self.assertEqual(err(m.parse_bundle_count, bad).code, ErrorCode.VALIDATION_ERROR, repr(bad))


class LineTotal(unittest.TestCase):
    def test_half_up_not_half_even(self):
        self.assertEqual(m.line_total(D("0.5"), D(1), D(0), D(0)), D(1))        # HALF_EVEN would give 0
        self.assertEqual(m.line_total(D("2.5"), D(1), D(0), D(0)), D(3))        # HALF_EVEN would give 2
        self.assertEqual((D("2.5") * 1).quantize(D(1), rounding=ROUND_HALF_EVEN), D(2))  # documents the trap
        self.assertEqual(m.line_total(D("10.000"), D(125000), D(0), D(0)), D(1250000))
        self.assertEqual(m.line_total(D("1.001"), D(1000), D(1), D(1)), D(1001))   # 1001.000 - 1 + 1 -> 1001

    def test_discount_above_gross(self):
        e = err(m.line_total, D(1), D(10), D(11), D(0))
        self.assertEqual(e.code, ErrorCode.AMOUNT_OUT_OF_RANGE)
        self.assertEqual(m.line_total(D(1), D(10), D(10), D(0)), D(0))           # equal is allowed

    def test_overflow(self):
        e = err(m.line_total, D("999999999999999.999"), D(10**20 - 1), D(0), D(0))
        self.assertEqual(e.code, ErrorCode.AMOUNT_OUT_OF_RANGE)
        self.assertEqual(m.line_total(D(1), D(10**20 - 1), D(0), D(0)), D(10**20 - 1))
        self.assertEqual(err(m.line_total, D(1), D(10**20 - 1), D(0), D(1)).code, ErrorCode.AMOUNT_OUT_OF_RANGE)

    def test_header_preview_range(self):
        big = m.Line(D(1), D(10**20 - 1), D(0), D(0))
        self.assertEqual(err(m.preview_header_totals, [big, big]).code, ErrorCode.AMOUNT_OUT_OF_RANGE)
        t = m.preview_header_totals([m.Line(D("2.5"), D(1), D(0), D(0)), m.Line(D("0.5"), D(1), D(0), D(0))])
        self.assertEqual((t.subtotal, t.grand_total), (D(4), D(4)))               # 3 + 1

    def test_money_str(self):
        self.assertEqual(m.money_str(D("1250000")), "1250000")
        self.assertEqual(m.money_str(D(0)), "0")


def _cases(n, seed=1405):
    rnd = random.Random(seed)
    rows = []
    for k in range(n):
        kind = k % 4
        if kind == 0:     # exact .5 ties: odd price x half quantity
            q = D(rnd.randint(0, 2000)) + D("0.5"); p = D(rnd.randrange(1, 10**9, 2))
        elif kind == 1:   # 3-decimal quantities, realistic prices
            q = D(rnd.randint(1, 10**7)) / 1000; p = D(rnd.randint(0, 10**9))
        elif kind == 2:   # near the 20-digit ceiling
            q = D(rnd.randint(10**5, 10**9 - 1)) / 1000; p = D(rnd.randint(10**11, 10**13))
        else:             # tiny, rounding-sensitive
            q = D(rnd.randint(1, 999)) / 1000; p = D(rnd.randint(1, 5000))
        gross = q * p
        d = D(rnd.randint(0, int(gross))) if gross >= 1 else D(0)
        if rnd.random() < 0.1:
            d = D(int(gross) + rnd.randint(1, 3))     # deliberately above gross
        t = D(rnd.randint(0, 10**9))
        rows.append((q.quantize(D("0.001")), p, d, t))
    for k in range(n // 30):          # extremes: ceiling of NUMERIC(20,0) and beyond, exercised on purpose
        q = D(rnd.randint(10**14, 10**18 - 1)) / 1000
        p = D(rnd.randint(10**13, 10**20 - 1))
        d = D(rnd.randint(0, 10**18)) if k % 3 else D(0)
        t = D(rnd.randint(0, 10**20 - 1)) if k % 2 else D(rnd.randint(0, 10**9))
        rows.append((q, p, d, t))
    return rows


@unittest.skipUnless(pg.available(), "SKIPPED: no PostgreSQL server reachable through psql")
class AgainstPostgreSQL(unittest.TestCase):
    """PostgreSQL is the live oracle: it recomputes every case itself; nothing is a stored expectation."""
    N = 6000

    def _run(self, rows, expr_sql):
        values = ",\n".join(f"({i},{q},{p},{d},{t},'{r}')" for i, (q, p, d, t, r) in enumerate(rows))
        sql = f"SELECT i, ({expr_sql}) FROM (VALUES {values}) AS c(i,q,p,d,t,r) ORDER BY i;"
        rc, out, errtxt = pg.psql("postgres", sql)
        self.assertEqual(rc, 0, errtxt)
        return [l.split("|") for l in out.strip().splitlines()]

    def test_line_total_6000_cases_equal_postgresql(self):
        cases = _cases(self.N)
        py = []
        for q, p, d, t in cases:
            try:
                py.append(("ok", m.line_total(q, p, d, t)))
            except AppError as e:
                py.append(("err", e.code))
        rows = [(q, p, d, t, "") for q, p, d, t in cases]
        pgrows = self._run(rows, "CASE WHEN d > q*p THEN 'DISCOUNT' "
                                 "WHEN ROUND(q*p - d + t, 0) >= 100000000000000000000::numeric THEN 'RANGE' "
                                 "ELSE ROUND(q*p - d + t, 0)::text END")
        mismatches = []
        kinds = {"ok": 0, "discount": 0, "range": 0}
        for (kind, val), (i, pgv) in zip(py, pgrows):
            if kind == "ok":
                kinds["ok"] += 1
                if str(val) != pgv: mismatches.append((i, val, pgv))
            else:
                kinds["discount" if pgv == "DISCOUNT" else "range"] += 1
                want = {"DISCOUNT", "RANGE"}
                if pgv not in want or val != ErrorCode.AMOUNT_OUT_OF_RANGE: mismatches.append((i, val, pgv))
        self.assertEqual(mismatches, [], mismatches[:5])
        self.assertGreater(kinds["ok"], 5000)
        self.assertGreater(kinds["discount"], 100)          # the error branch is really exercised
        print(f"\n  [money] {len(cases)} cases vs live PostgreSQL: 0 mismatches; accepted={kinds['ok']} "
              f"discount>gross={kinds['discount']} out-of-range={kinds['range']}")

    def test_half_even_would_have_failed(self):
        """Evidence that the test can fail: the forbidden HALF_EVEN differs from PostgreSQL on tie cases."""
        cases = [c for c in _cases(2000) if c[2] <= c[0] * c[1]][:1000]
        rows = [(q, p, d, t, "") for q, p, d, t in cases]
        pgrows = self._run(rows, "ROUND(q*p - d + t, 0)::text")
        diff = sum(1 for (q, p, d, t), (_, pgv) in zip(cases, pgrows)
                   if str((q * p - d + t).quantize(D(1), rounding=ROUND_HALF_EVEN)) != pgv)
        self.assertGreater(diff, 0)

    def test_header_totals_preview_equals_trigger_formula(self):
        rnd = random.Random(7)
        mism = 0
        for _ in range(200):
            lines = []
            for _ in range(rnd.randint(1, 6)):
                q = D(rnd.randint(1, 10**6)) / 1000; p = D(rnd.randint(0, 10**8))
                d = D(rnd.randint(0, int(q * p))) if q * p >= 1 else D(0)
                lines.append(m.Line(q.quantize(D("0.001")), p, d, D(rnd.randint(0, 10**6))))
            t = m.preview_header_totals(lines)
            vals = ",".join(f"({l.quantity},{l.unit_price},{l.discount_amount},{l.tax_amount})" for l in lines)
            rc, out, e = pg.psql("postgres",
                f"SELECT SUM(ROUND(q*p,0)), SUM(d), SUM(t), SUM(ROUND(q*p - d + t,0)) FROM (VALUES {vals}) AS x(q,p,d,t);")
            self.assertEqual(rc, 0, e)
            got = tuple(D(x) for x in out.strip().split("|"))
            if got != (t.subtotal, t.discount_total, t.tax_total, t.grand_total): mism += 1
        self.assertEqual(mism, 0)

    def test_ceiling_matches_numeric_20_0(self):
        rc, out, e = pg.psql("postgres", f"SELECT ({10**20 - 1})::numeric(20,0)::text")
        self.assertEqual(out.strip(), str(10**20 - 1))
        rc, out, e = pg.psql("postgres", f"SELECT ({10**20})::numeric(20,0)")
        self.assertNotEqual(rc, 0); self.assertIn("numeric field overflow", e)


if __name__ == "__main__":
    unittest.main()
