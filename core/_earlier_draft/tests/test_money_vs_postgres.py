"""Service money function vs the REAL database.

What this proves (and what it does not):
  * For every generated case, the Service verdict (accept / reject) equals the verdict of the real item INSERT
    (CHECK constraints + header-total trigger of 001/002), and for accepted cases line_total is accepted verbatim by
    chk_request_items_line_total_consistency, i.e. the DB's own ROUND() agrees.
  * Cases: random realistic, exact .5 ties, 3-decimal quantities, boundary values around 10^20, discount == / > gross.
  * It is a differential test over those inputs, not a proof for all inputs. The domain argument: PostgreSQL ROUND on
    NUMERIC rounds half away from zero, equal to ROUND_HALF_UP for the non-negative values the Service allows.
"""
import random, unittest
from decimal import Decimal as D

from tradeflow_core import money as m
from tradeflow_core.errors import DomainError
from . import pg_support as pg


def gen_cases(seed=1405, n=6000):
    rnd = random.Random(seed)
    rows = []
    for _ in range(n // 6):                                           # exact ties
        rows.append((D(rnd.randint(0, 2000)) + D("0.5"), D(rnd.randrange(1, 10**9, 2)), None, D(rnd.randint(0, 10**6))))
    for _ in range(n // 3):                                           # realistic
        rows.append((D(rnd.randint(1, 10**7)) / 1000, D(rnd.randint(0, 10**9)), None, D(rnd.randint(0, 10**9))))
    for _ in range(n // 6):                                           # large, still fitting
        rows.append((D(rnd.randint(10**5, 10**9 - 1)) / 1000, D(rnd.randint(10**11, 10**13)), None, D(rnd.randint(0, 10**9))))
    for _ in range(n // 6):                                           # around the 20-digit boundary
        p = D(rnd.choice([10**20 - 1, 10**19, 10**19 + 7, 5 * 10**19, 99999999999999999999]))
        q = rnd.choice([D(1), D("1.001"), D("0.5"), D("2"), D("0.001"), D("10.000")])
        rows.append((q, p, None, D(rnd.choice([0, 1, 10**19, 10**20 - 1]))))
    out = []
    for q, p, d, t in rows:
        g = q * p
        kind = rnd.random()
        if kind < .55:   d = D(rnd.randint(0, int(min(g, 10**20 - 1))))
        elif kind < .70: d = min(D(10**20 - 1), g.quantize(D(1)))          # about equal to gross
        elif kind < .85: d = min(D(10**20 - 1), g.quantize(D(1)) + D(rnd.randint(1, 5)))   # slightly above gross
        else:            d = D(0)
        out.append((q, p, d, t))
    while len(out) < n:
        out.append((D("1"), D("1"), D("0"), D("0")))
    return out[:n]


@pg.requires_pg
class MoneyVsPostgres(unittest.TestCase):
    N = 6000

    def test_service_verdict_equals_database_verdict(self):
        db = pg.fresh_db("tf_core_money")
        ids = pg.psql(db, """select (select id from organizations), (select id from customers), (select id from users where username='admin'),
                                    (select id from products), (select id from units where code='KG')""").strip().split("|")
        org, cust, usr, prod, unit = ids
        pg.psql(db, f"""insert into purchase_requests(id,organization_id,request_number,customer_id,created_by)
                       values ('00000000-0000-0000-0000-0000000000a1','{org}','T-1','{cust}','{usr}')""")
        cases = gen_cases(n=self.N)
        expected = []
        values = []
        for i, (q, p, d, t) in enumerate(cases):
            try:
                lt = m.compute_line_total(q, p, d, t)
                expected.append("OK")
            except DomainError as e:
                lt = D(0)
                expected.append("REJECT")
            values.append(f"({i},{q},{p},{d},{t},{lt})")
        sql = f"""
CREATE TEMP TABLE cc(i int, q numeric, p numeric, d numeric, t numeric, lt numeric);
INSERT INTO cc VALUES {",".join(values)};
CREATE TEMP TABLE res(i int, verdict text, state text);
DO $$ DECLARE r record; v text; BEGIN
 FOR r IN SELECT * FROM cc ORDER BY i LOOP
  v := 'REJECT';
  BEGIN
    INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,unit_id,quantity,unit_price,discount_amount,tax_amount,line_total)
    VALUES ('{org}','00000000-0000-0000-0000-0000000000a1','{prod}','{unit}',r.q,r.p,r.d,r.t,r.lt);
    v := 'OK';
    RAISE EXCEPTION 'rollback this case' USING ERRCODE='P0001';
  EXCEPTION
    WHEN SQLSTATE 'P0001' THEN NULL;
    WHEN OTHERS THEN v := 'REJECT';
  END;
  INSERT INTO res VALUES (r.i, v, '');
 END LOOP; END $$;
SELECT i||':'||verdict||':'||state FROM res ORDER BY i;
"""
        open("/tmp/_tf_money.sql", "w").write(sql)
        out = pg.psql(db, file="/tmp/_tf_money.sql").split()
        got = {int(x.split(":")[0]): x.split(":")[1] for x in out}
        self.assertEqual(len(got), self.N)
        mism = [(i, cases[i], expected[i], got[i]) for i in range(self.N) if expected[i] != got[i]]
        self.assertEqual(mism[:5], [], f"{len(mism)} verdict mismatches")
        n_ok = expected.count("OK"); n_rej = expected.count("REJECT")
        print(f"\n  money vs PostgreSQL: {self.N} cases, accepted={n_ok}, rejected={n_rej}, mismatches=0")
        self.assertGreater(n_ok, 3000); self.assertGreater(n_rej, 100)

    def test_rounding_equals_postgres_round(self):
        db = pg.fresh_db("tf_core_money2", seeds=False)
        cases = [c for c in gen_cases(seed=7, n=3000)]
        vals, exp = [], []
        for i, (q, p, d, t) in enumerate(cases):
            if d > q * p: d = D(0)
            lt = m.line_total(q, p, d, t)
            vals.append(f"({i},{q},{p},{d},{t},{lt})")
        r = pg.psql(db, f"""CREATE TEMP TABLE cc(i int,q numeric,p numeric,d numeric,t numeric,lt numeric);
                            INSERT INTO cc VALUES {",".join(vals)};
                            SELECT count(*), count(*) FILTER (WHERE round(q*p-d+t,0) <> lt) FROM cc;""").strip().split("\n")[-1]
        self.assertEqual(r, "3000|0")


if __name__ == "__main__":
    unittest.main()
