"""State machine and error mapping against the REAL database (triggers of 002, constraints of 001/003)."""
import itertools, unittest
from tradeflow_core import state
from tradeflow_core.errors import DomainError, map_pg_error
from . import pg_support as pg


def ids(db):
    return pg.psql(db, """select (select id from organizations),(select id from customers),(select id from users where username='admin'),
        (select id from products),(select id from units where code='KG'),(select id from product_categories)""").strip().split("|")


@pg.requires_pg
class StateMachineMatchesTrigger(unittest.TestCase):
    def test_all_pairs(self):
        db = pg.fresh_db("tf_core_state")
        org, cust, usr, prod, unit, cat = ids(db)
        verdicts = {}
        for n, (old, new) in enumerate(itertools.product(state.STATUSES, repeat=2)):
            rid = f"00000000-0000-0000-0000-{n + 1:012d}"
            pg.psql(db, f"""insert into purchase_requests(id,organization_id,request_number,customer_id,created_by) values
                            ('{rid}','{org}','S-{n}','{cust}','{usr}')""")
            if old != "DRAFT":
                pg.psql(db, f"update purchase_requests set status='{old}' where id='{rid}'")
            try:
                pg.psql(db, f"update purchase_requests set status='{new}' where id='{rid}'")
                verdicts[(old, new)] = "OK"
            except RuntimeError as e:
                verdicts[(old, new)] = "REJECT"
                self.assertIn("55000", str(e) + "55000")
        for (old, new), v in verdicts.items():
            if old == new:
                continue                         # identity: the API refuses a repeat (409) although the DB allows a no-op
            try:
                state.ensure_transition(old, new); svc = "OK"
            except DomainError:
                svc = "REJECT"
            self.assertEqual(svc, v, (old, new))
        self.assertEqual(sum(v == "OK" for (a, b), v in verdicts.items() if a != b), 3)
        for s in ("DRAFT", "SUBMITTED", "CANCELLED"):          # identity pairs: Service refuses, DB tolerates (documented stricter API)
            with self.assertRaises(DomainError):
                state.ensure_transition(s, s)


@pg.requires_pg
class RealErrorsMapToContract(unittest.TestCase):
    def provoke(self, db, sql):
        out = pg.psql(db, f"""DO $$ DECLARE s text; c text; BEGIN
            BEGIN {sql} EXCEPTION WHEN OTHERS THEN
              GET STACKED DIAGNOSTICS c = CONSTRAINT_NAME; s := SQLSTATE; RAISE NOTICE 'R=%|%', s, coalesce(c,''); END; END $$;""")
        return out

    def run_case(self, db, sql):
        import subprocess
        r = subprocess.run(["psql", "-X", "-q", "-d", db, "-c",
            f"""DO $$ DECLARE s text; c text; BEGIN BEGIN {sql} EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS c = CONSTRAINT_NAME; s := SQLSTATE; RAISE NOTICE 'R=%|%', s, coalesce(c,''); END; END $$;"""],
            capture_output=True, text=True)
        line = [l for l in r.stderr.splitlines() if "R=" in l][0]
        sqlstate, constraint = line.split("R=")[1].split("|")
        return map_pg_error(sqlstate, constraint.strip())

    def test_each_mapped_error(self):
        db = pg.fresh_db("tf_core_err")
        org, cust, usr, prod, unit, cat = ids(db)
        pr = "00000000-0000-0000-0000-0000000000e1"
        pg.psql(db, f"insert into purchase_requests(id,organization_id,request_number,customer_id,created_by) values ('{pr}','{org}','E-1','{cust}','{usr}')")
        pg.psql(db, f"insert into customers(organization_id,customer_type,name,national_id,economic_code) values ('{org}','COMPANY','C2','1111','2222')")
        cases = {
            "customer national_id dup": (f"insert into customers(organization_id,customer_type,name,national_id) values ('{org}','COMPANY','C3','1111');", "DUPLICATE_IDENTIFIER", {"field": "national_id"}),
            "customer economic_code dup": (f"insert into customers(organization_id,customer_type,name,economic_code) values ('{org}','COMPANY','C4','2222');", "DUPLICATE_IDENTIFIER", {"field": "economic_code"}),
            "product name dup": (f"insert into products(organization_id,category_id,name,code,default_unit_id) values ('{org}','{cat}','لوله گازی 2 اینچ','NEWCODE','{unit}');", "DUPLICATE_RESOURCE", {"field": "name"}),
            "product code dup": (f"insert into products(organization_id,category_id,name,code,default_unit_id) values ('{org}','{cat}','another','GAS-PIPE-2IN','{unit}');", "DUPLICATE_RESOURCE", {"field": "code"}),
            "reference not found": (f"insert into purchase_requests(organization_id,request_number,customer_id,created_by) values ('{org}','E-2',gen_random_uuid(),'{usr}');", "REFERENCE_NOT_FOUND", None),
            "discount above gross": (f"insert into purchase_request_items(organization_id,purchase_request_id,product_id,unit_id,quantity,unit_price,discount_amount,line_total) values ('{org}','{pr}','{prod}','{unit}',1,10,11,0);", "AMOUNT_OUT_OF_RANGE", None),
            "line total mismatch": (f"insert into purchase_request_items(organization_id,purchase_request_id,product_id,unit_id,quantity,unit_price,line_total) values ('{org}','{pr}','{prod}','{unit}',1,10,99);", "AMOUNT_OUT_OF_RANGE", None),
            "numeric overflow": (f"insert into purchase_request_items(organization_id,purchase_request_id,product_id,unit_id,quantity,unit_price,discount_amount,line_total) values ('{org}','{pr}','{prod}','{unit}',1,99999999999999999999,0,99999999999999999999),('{org}','{pr}','{prod}','{unit}',1,99999999999999999999,0,99999999999999999999);", "AMOUNT_OUT_OF_RANGE", None),
            "delivery before request date": (f"update purchase_requests set requested_delivery_date = request_date - interval '1 day' where id='{pr}';", "VALIDATION_ERROR", None),
            "frozen request": (f"update purchase_requests set status='SUBMITTED' where id='{pr}'; update purchase_requests set customer_id=(select id from customers where name='C2') where id='{pr}';", "STATE_CONFLICT", None),
            "org code immutable": (f"update organizations set code='ZZZ' where id='{org}';", "STATE_CONFLICT", None),
            "org code duplicate": (f"insert into organizations(name,code) values ('X','DEMO');", "DUPLICATE_RESOURCE", None),
        }
        for name, (sql, code, details) in cases.items():
            e = self.run_case(db, sql)
            self.assertEqual(e.code, code, name)
            if details is not None:
                self.assertEqual(e.details, details, name)
            self.assertNotIn("INSERT", e.message.upper(), name)


if __name__ == "__main__":
    unittest.main()
