"""The snapshot the Service builds is accepted by the REAL trigger of migration 002 (C6), and a wrong one is not."""
import json, unittest
from tradeflow_core.specifications import FieldDef, build_snapshot
from . import pg_support as pg


@pg.requires_pg
class SnapshotAcceptedByDatabase(unittest.TestCase):
    def test_roundtrip(self):
        db = pg.fresh_db("tf_core_spec")
        org, cust, usr, prod, unit = pg.psql(db, """select (select id from organizations),(select id from customers),
            (select id from users where username='admin'),(select id from products),(select id from units where code='KG')""").strip().split("|")
        rows = pg.psql(db, "select id,code,name,data_type,is_active,is_required,coalesce(options::text,'') from product_specification_fields").strip().splitlines()
        fields = {}
        for r in rows:
            i, c, n, t, a, req, o = r.split("|")
            fields[i] = FieldDef(i, c, n, t, a == "t", req == "t", tuple(json.loads(o)) if o else None)
        by_code = {f.code: f for f in fields.values()}
        snap = build_snapshot([{"field_id": by_code["DIAMETER"].id, "value": "2"},
                               {"field_id": by_code["THICKNESS_MM"].id, "value": "2.50"},
                               {"field_id": by_code["GRADE"].id, "value": " St37 "}], fields, set(fields))
        self.assertEqual([e["value"] for e in snap], ["2", "2.5", "St37"])
        pg.psql(db, f"""insert into purchase_requests(id,organization_id,request_number,customer_id,created_by)
                       values ('00000000-0000-0000-0000-0000000000b1','{org}','T-1','{cust}','{usr}')""")
        ins = lambda s: pg.psql(db, f"""insert into purchase_request_items(organization_id,purchase_request_id,product_id,unit_id,quantity,specifications)
                  values ('{org}','00000000-0000-0000-0000-0000000000b1','{prod}','{unit}',1,$j${json.dumps(s, ensure_ascii=False)}$j$::jsonb)""")
        ins(snap)                                                         # accepted
        bad = [dict(snap[0], data_type="TEXT")]                           # the DB checks code/data_type against the field
        with self.assertRaises(RuntimeError) as c:
            ins(bad)
        self.assertIn("unknown field", str(c.exception))                  # trigger C6: code/data_type must match the field
        with self.assertRaises(RuntimeError):
            ins([snap[0], snap[0]])                                       # duplicates are refused too


if __name__ == "__main__":
    unittest.main()
