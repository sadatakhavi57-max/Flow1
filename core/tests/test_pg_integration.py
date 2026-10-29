"""Real PostgreSQL: every database error class the contract maps (section 15) is provoked and fed to map_pg_error,
and an audit entry built by the core is inserted into the real, append-only audit_logs."""
import json
import os
import unittest

from tradeflow_core import audit
from tradeflow_core.errors import ErrorCode, map_pg_error
from . import pg

SQL_DIR = os.environ.get("TF_SQL_DIR")


_DB_READY = set()


def _ensure_db(name):
    if name not in _DB_READY:
        pg.make_db(name, SQL_DIR)
        _DB_READY.add(name)


@unittest.skipUnless(pg.available() and SQL_DIR, "SKIPPED: needs PostgreSQL via psql and TF_SQL_DIR")
class RealDatabaseErrors(unittest.TestCase):
    DB = "tf_core_pg"

    @classmethod
    def setUpClass(cls):
        _ensure_db(cls.DB)
        rc, out, e = pg.psql(cls.DB, """
          SELECT o.id, p.id, u.id, c.id, usr.id FROM organizations o
            JOIN products p ON p.organization_id=o.id AND p.code='GAS-PIPE-2IN'
            JOIN units u ON u.organization_id=o.id AND u.code='KG'
            JOIN customers c ON c.organization_id=o.id
            JOIN users usr ON usr.organization_id=o.id AND usr.username='admin' WHERE o.code='DEMO'""")
        assert rc == 0, e
        cls.org, cls.prod, cls.unit, cls.cust, cls.admin = out.strip().split("|")
        rc, out, e = pg.psql(cls.DB, f"""
          INSERT INTO purchase_requests (organization_id, request_number, customer_id, created_by, updated_by)
          VALUES ('{cls.org}','1405-000001','{cls.cust}','{cls.admin}','{cls.admin}') RETURNING id""")
        assert rc == 0, e
        cls.req = out.strip().splitlines()[0]

    def provoke(self, setup_sql: str, failing_sql: str):
        """Runs setup (kept inside the transaction) then the failing statement in a sub-block; returns (sqlstate, constraint, message).
        Everything is rolled back, so tests never pollute each other."""
        body = f"""BEGIN;
        {setup_sql}
        DO $$ DECLARE s TEXT; c TEXT; m TEXT; BEGIN
          BEGIN {failing_sql}; RAISE NOTICE 'RES|NONE||';
          EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS s = RETURNED_SQLSTATE, c = CONSTRAINT_NAME, m = MESSAGE_TEXT;
            RAISE NOTICE 'RES|%|%|%', s, coalesce(c,''), replace(m, E'\\n', ' ');
          END;
        END $$;
        ROLLBACK;"""
        rc, out, err = pg.psql(self.DB, body)
        self.assertEqual(rc, 0, err)
        line = next(l for l in err.splitlines() if "RES|" in l)
        s, c, m = line.split("RES|", 1)[1].split("|", 2)
        self.assertNotEqual(s, "NONE", f"statement unexpectedly succeeded: {failing_sql}")
        return s, c or None, m

    def mapped(self, setup, failing):
        s, c, m = self.provoke(setup, failing)
        e = map_pg_error(s, c, m)
        return s, c, e

    def item(self, **over):
        cols = dict(quantity="1", unit_price="10", discount_amount="0", tax_amount="0", line_total="10", bundle_count="0")
        cols.update(over)
        names = ",".join(cols); vals = ",".join(str(v) for v in cols.values())
        return (f"INSERT INTO purchase_request_items (organization_id, purchase_request_id, product_id, unit_id, {names}) "
                f"VALUES ('{self.org}','{self.req}','{self.prod}','{self.unit}',{vals})")

    def test_state_conflicts_55000(self):
        s, c, e = self.mapped(f"UPDATE purchase_requests SET status='SUBMITTED' WHERE id='{self.req}';", self.item())
        self.assertEqual((s, e.code), ("55000", ErrorCode.STATE_CONFLICT))                  # item added after submit
        s, c, e = self.mapped(f"UPDATE purchase_requests SET status='CANCELLED' WHERE id='{self.req}';",
                              f"UPDATE purchase_requests SET status='SUBMITTED' WHERE id='{self.req}'")
        self.assertEqual((s, e.code), ("55000", ErrorCode.STATE_CONFLICT))                  # CANCELLED -> SUBMITTED
        s, c, e = self.mapped("", f"UPDATE organizations SET code='X-1' WHERE id='{self.org}'")
        self.assertEqual((s, e.code), ("55000", ErrorCode.STATE_CONFLICT))                  # immutable organizations.code (003)

    def test_duplicates_23505(self):
        base = (f"INSERT INTO customers (organization_id, customer_type, name, {{col}}) VALUES ('{self.org}','COMPANY','A','V1');")
        for col, field in [("national_id", "national_id"), ("economic_code", "economic_code")]:
            s, c, e = self.mapped(base.format(col=col),
                                  f"INSERT INTO customers (organization_id, customer_type, name, {col}) VALUES ('{self.org}','COMPANY','B','V1')")
            self.assertEqual((s, e.code, e.details), ("23505", ErrorCode.DUPLICATE_IDENTIFIER, {"field": field}), (col, c))
        prod = (f"INSERT INTO products (organization_id, category_id, name, code, default_unit_id) "
                f"SELECT organization_id, category_id, '{{n}}', '{{c}}', default_unit_id FROM products WHERE id='{self.prod}'")
        s, c, e = self.mapped("", prod.format(n="new name", c="GAS-PIPE-2IN"))
        self.assertEqual((e.code, e.details), (ErrorCode.DUPLICATE_RESOURCE, {"field": "code"}))
        s, c, e = self.mapped("", prod.format(n="لوله گازی 2 اینچ", c="NEWCODE"))
        self.assertEqual((e.code, e.details), (ErrorCode.DUPLICATE_RESOURCE, {"field": "name"}))
        s, c, e = self.mapped("", f"INSERT INTO purchase_requests (organization_id, request_number, customer_id, created_by, updated_by) "
                                  f"VALUES ('{self.org}','1405-000001','{self.cust}','{self.admin}','{self.admin}')")
        self.assertEqual((s, e.code), ("23505", ErrorCode.DUPLICATE_RESOURCE))              # request_number clash

    def test_references_23503(self):
        s, c, e = self.mapped("", self.item().replace(f"'{self.prod}'", "'00000000-0000-0000-0000-000000000001'"))
        self.assertEqual((s, e.code), ("23503", ErrorCode.REFERENCE_NOT_FOUND))
        # a product of ANOTHER organization is indistinguishable from a missing one (composite same-organization FK)
        other = ("INSERT INTO organizations (name, code) VALUES ('Other','OTHER-1');"
                 "INSERT INTO product_categories (organization_id, name, code) SELECT id,'c','C' FROM organizations WHERE code='OTHER-1';"
                 "INSERT INTO units (organization_id, name, code, unit_type) SELECT id,'u','U','WEIGHT' FROM organizations WHERE code='OTHER-1';"
                 "INSERT INTO products (organization_id, category_id, name, code, default_unit_id) "
                 "SELECT o.id, pc.id, 'p','P', u.id FROM organizations o JOIN product_categories pc ON pc.organization_id=o.id "
                 "JOIN units u ON u.organization_id=o.id WHERE o.code='OTHER-1';")
        failing = (f"INSERT INTO purchase_request_items (organization_id, purchase_request_id, product_id, unit_id, quantity) "
                   f"SELECT '{self.org}','{self.req}', p.id, '{self.unit}', 1 FROM products p WHERE p.code='P'")
        s, c, e = self.mapped(other, failing)
        self.assertEqual((s, e.code), ("23503", ErrorCode.REFERENCE_NOT_FOUND))

    def test_amount_and_field_checks_23514_22003(self):
        s, c, e = self.mapped("", self.item(unit_price="10", discount_amount="11", line_total="0"))
        self.assertEqual((s, c, e.code), ("23514", "chk_request_items_discount_not_exceed", ErrorCode.AMOUNT_OUT_OF_RANGE))
        s, c, e = self.mapped("", self.item(line_total="9"))
        self.assertEqual((s, c, e.code), ("23514", "chk_request_items_line_total_consistency", ErrorCode.AMOUNT_OUT_OF_RANGE))
        s, c, e = self.mapped("", self.item(unit_price="-1", line_total="0"))
        self.assertEqual((s, e.code), ("23514", ErrorCode.AMOUNT_OUT_OF_RANGE))
        s, c, e = self.mapped("", self.item(quantity="0", line_total="0"))
        self.assertEqual((s, c, e.code, e.details), ("23514", "chk_request_items_quantity", ErrorCode.VALIDATION_ERROR,
                                                     [{"field": "quantity", "reason": "MUST_BE_POSITIVE"}]))
        s, c, e = self.mapped("", self.item(bundle_count="-1"))
        self.assertEqual((c, e.code), ("chk_request_items_bundle_count", ErrorCode.VALIDATION_ERROR))
        s, c, e = self.mapped("", self.item(unit_price="100000000000000000000", line_total="0"))
        self.assertEqual((s, e.code), ("22003", ErrorCode.AMOUNT_OUT_OF_RANGE))              # NUMERIC(20,0) overflow
        s, c, e = self.mapped("", f"UPDATE purchase_requests SET requested_delivery_date = DATE '2000-01-01' WHERE id='{self.req}'")
        self.assertEqual((s, c, e.code, e.details), ("23514", "chk_purchase_requests_delivery_date", ErrorCode.VALIDATION_ERROR,
                                                     [{"field": "requested_delivery_date", "reason": "BEFORE_REQUEST_DATE"}]))

    def test_snapshot_trigger_errors_are_internal_not_client_errors(self):
        for snap in ['[{"field_id":"7","field_code":"X","field_name":"X","data_type":"TEXT","value":"a"}]',          # 23514
                     '[{"field_id":"00000000-0000-0000-0000-000000000009","field_code":"X","field_name":"X","data_type":"TEXT","value":"a"}]']:  # 23503
            s, c, e = self.mapped("", self.item().replace("VALUES (", "VALUES (").replace(") VALUES", ", specifications) VALUES")
                                  .rstrip(")") + f", '{snap}'::jsonb)")
            self.assertIn(s, ("23514", "23503"))
            self.assertEqual(e.code, ErrorCode.INTERNAL_ERROR, s)                         # the Service wrote it: a bug, never the client's fault

    def test_no_server_text_leaks_into_the_error(self):
        s, c, m = self.provoke("", self.item(unit_price="10", discount_amount="11", line_total="0"))
        body = json.dumps(map_pg_error(s, c, m).to_body("rid"))
        for leak in ["violates", "purchase_request_items", "DETAIL", "Failing row", "chk_"]:
            self.assertNotIn(leak, body)

    def test_unmapped_and_availability_classes(self):
        self.assertEqual(map_pg_error("XX000").code, ErrorCode.INTERNAL_ERROR)
        self.assertEqual(map_pg_error("42P01").code, ErrorCode.INTERNAL_ERROR)             # undefined table: never echoed
        for st in ["40P01", "40001"]:
            e = map_pg_error(st); self.assertEqual((e.code, e.retryable), (ErrorCode.TEMPORARILY_UNAVAILABLE, True))
        for st in ["08006", "57P01", "53300"]:
            e = map_pg_error(st); self.assertEqual((e.code, e.retryable), (ErrorCode.TEMPORARILY_UNAVAILABLE, False))

    def test_real_deadlock_class_is_40P01(self):
        """Evidence that 40P01 is what PostgreSQL really raises for a deadlock (two sessions locking in opposite order)."""
        import subprocess, time
        rc, out, e = pg.psql(self.DB, f"""INSERT INTO customers (organization_id, customer_type, name) VALUES
            ('{self.org}','COMPANY','DL1'), ('{self.org}','COMPANY','DL2');""")
        self.assertEqual(rc, 0, e)
        def sess(a, b):
            sql = (f"BEGIN; SELECT 1 FROM customers WHERE name='{a}' FOR UPDATE; SELECT pg_sleep(1.5); "
                   f"SELECT 1 FROM customers WHERE name='{b}' FOR UPDATE; COMMIT;")
            return subprocess.Popen(["psql", "-X", "-q", "-d", self.DB, "-v", "VERBOSITY=verbose"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True), sql
        import threading
        (p1, s1), (p2, s2) = sess("DL1", "DL2"), sess("DL2", "DL1")
        res = {}
        th = [threading.Thread(target=lambda k=k, p=p, s=s: res.__setitem__(k, p.communicate(s))) for k, (p, s) in enumerate([(p1, s1), (p2, s2)])]
        [x.start() for x in th]; [x.join() for x in th]                  # both sessions run at the same time
        errs = res[0][1] + res[1][1]
        self.assertIn("40P01", errs)
        pg.psql(self.DB, "DELETE FROM customers WHERE name IN ('DL1','DL2')")


@unittest.skipUnless(pg.available() and SQL_DIR, "SKIPPED: needs PostgreSQL via psql and TF_SQL_DIR")
class RealAuditTable(unittest.TestCase):
    DB = "tf_core_pg"

    @classmethod
    def setUpClass(cls):
        _ensure_db(cls.DB)

    def test_entries_built_by_the_core_insert_and_the_table_stays_append_only(self):
        rc, out, e = pg.psql(self.DB, "SELECT o.id, u.id FROM organizations o JOIN users u ON u.organization_id=o.id AND u.username='admin' WHERE o.code='DEMO'")
        self.assertEqual(rc, 0, e)
        org, usr = out.strip().split("|")
        n = 0
        for action, entity in [(a, en) for a in audit.AuditAction for en in audit.AuditEntity]:
            ent = audit.build_entry(action.value, entity.value, organization_id=org, user_id=usr, entity_id=usr,
                                    old_data={"a": 1}, new_data={"b": "ی"}, description="t", ip_address="203.0.113.5")
            cols = ",".join(ent); vals = ",".join("NULL" if v is None else "'" + (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v)).replace("'", "''") + "'" for v in ent.values())
            rc, out, e = pg.psql(self.DB, f"INSERT INTO audit_logs ({cols}) VALUES ({vals})")
            self.assertEqual(rc, 0, f"{action}/{entity}: {e}")
            n += 1
        self.assertEqual(n, len(audit.AuditAction) * len(audit.AuditEntity))      # every action x entity (11 x 6 since Stage 4)
        for stmt in ["UPDATE audit_logs SET description='x'", "DELETE FROM audit_logs", "TRUNCATE audit_logs"]:
            rc, out, e = pg.psql(self.DB, stmt)
            self.assertNotEqual(rc, 0, stmt)


if __name__ == "__main__":
    unittest.main()
