import json
import os
import unittest
import uuid

from tradeflow_core.errors import AppError, ErrorCode
from tradeflow_core.specs import FieldDef, build_snapshot, canonical_value, missing_required, _Invalid
from . import pg

SQL_DIR = os.environ.get("TF_SQL_DIR")


def F(code, t, **kw):
    return FieldDef(id=str(uuid.uuid4()), code=code, name=code.title(), data_type=t, **kw)


def val(f, v):
    return canonical_value(f, v)


def bad(f, v):
    try:
        canonical_value(f, v)
    except _Invalid:
        return True
    return False


class Values(unittest.TestCase):          # the exact cases listed at the end of section 12
    def test_decimal(self):
        f = F("D", "DECIMAL")
        self.assertEqual(val(f, "125.50"), "125.5")
        self.assertEqual(val(f, "3.0"), "3")
        self.assertEqual(val(f, "2.50"), "2.5")
        self.assertEqual(val(f, "007.10"), "7.1")
        self.assertEqual(val(f, "-0.0"), "0")
        self.assertEqual(val(f, "-1.50"), "-1.5")
        self.assertEqual(val(f, "۲٫۵"), "2.5")                      # Persian digit + Arabic separator
        self.assertEqual(val(f, "1" * 12 + "." + "1" * 6), "1" * 12 + "." + "1" * 6)
        for v in ["ABC", "1,5", "", ".5", "5.", "1" * 13, "1.1234567", 2.5, 3, None, True]:
            self.assertTrue(bad(f, v), repr(v))

    def test_number(self):
        f = F("N", "NUMBER")
        self.assertEqual(val(f, "10"), "10")
        self.assertEqual(val(f, "۱۰"), "10")
        self.assertEqual(val(f, "-0"), "0")
        self.assertEqual(val(f, "-007"), "-7")
        self.assertEqual(val(f, "9" * 18), "9" * 18)
        for v in ["10.5", "9" * 19, "", "1e3", 10, 10.0, None, True]:
            self.assertTrue(bad(f, v), repr(v))

    def test_boolean(self):
        f = F("B", "BOOLEAN")
        self.assertIs(val(f, True), True); self.assertIs(val(f, False), False)
        for v in ["true", "1", 1, 0, None, "false", "yes"]:
            self.assertTrue(bad(f, v), repr(v))

    def test_date(self):
        f = F("T", "DATE")
        self.assertEqual(val(f, "2026-10-08"), "2026-10-08")
        self.assertEqual(val(f, "۲۰۲۶-۱۰-۰۸"), "2026-10-08")
        self.assertEqual(val(f, "2028-02-29"), "2028-02-29")
        for v in ["2026-02-30", "2027-02-29", "2026-13-01", "26-10-08", "2026/10/08", "1405-07-16x", "", 20261008]:
            self.assertTrue(bad(f, v), repr(v))

    def test_select(self):
        f = F("S", "SELECT", options=("A", "B"))
        self.assertEqual(val(f, "A"), "A")
        for v in ["C", "a", "", ["A"], None]:
            self.assertTrue(bad(f, v), repr(v))

    def test_multi_select_canonical_order_and_duplicates(self):
        f = F("M", "MULTI_SELECT", options=("A", "B", "C"))
        self.assertEqual(val(f, ["C", "A"]), ["A", "C"])           # order of the field's options
        for v in [["A", "A"], ["A", "X"], [], "A", ["A", 1], None]:
            self.assertTrue(bad(f, v), repr(v))

    def test_text(self):
        f = F("X", "TEXT")
        self.assertEqual(val(f, "  St37  "), "St37")
        self.assertEqual(val(f, "x" * 1000), "x" * 1000)
        self.assertEqual(val(f, "گرید ۱۲"), "گرید ۱۲")                # digits in free text are NOT rewritten
        for v in ["", "   ", "x" * 1001, 5, None]:
            self.assertTrue(bad(f, v), repr(v))

    def test_select_options_are_validated_at_definition(self):
        with self.assertRaises(ValueError): F("S", "SELECT")
        with self.assertRaises(ValueError): F("S", "SELECT", options=())
        with self.assertRaises(ValueError): F("Z", "FLOAT")


class Snapshot(unittest.TestCase):
    def setUp(self):
        self.dia = F("DIAMETER", "SELECT", options=("1/2", "1", "2"), is_required=True)
        self.th = F("THICKNESS", "DECIMAL")
        self.off = F("OLD", "TEXT", is_active=False)
        self.other = F("OTHERCAT", "TEXT")                           # exists, not applicable
        self.fields = {f.id: f for f in (self.dia, self.th, self.off, self.other)}
        self.app = [self.dia.id, self.th.id, self.off.id]

    def build(self, inputs):
        return build_snapshot(inputs, self.fields, self.app)

    def reasons(self, inputs):
        try:
            self.build(inputs)
        except AppError as e:
            self.assertEqual(e.code, ErrorCode.SPECIFICATION_INVALID)
            return [(d["field_id"], d["reason"]) for d in e.details]
        self.fail("no error")

    def test_success_builds_full_snapshot_in_input_order(self):
        s = self.build([{"field_id": self.th.id, "value": "2.50"}, {"field_id": self.dia.id.upper(), "value": "2"}])
        self.assertEqual(s[0], {"field_id": self.th.id, "field_code": "THICKNESS", "field_name": "Thickness",
                                "data_type": "DECIMAL", "value": "2.5"})
        self.assertEqual([e["field_code"] for e in s], ["THICKNESS", "DIAMETER"])
        self.assertEqual(self.build([]), [])

    def test_reason_vocabulary_and_order(self):
        ghost = str(uuid.uuid4())
        got = self.reasons([{"field_id": ghost, "value": "x"}, {"field_id": self.other.id, "value": "x"},
                            {"field_id": self.off.id, "value": "x"}, {"field_id": self.th.id, "value": "1"},
                            {"field_id": self.th.id, "value": "2"}, {"field_id": self.dia.id, "value": "99"}])
        self.assertEqual(got, [(ghost, "UNKNOWN_FIELD"), (self.other.id, "NOT_APPLICABLE"), (self.off.id, "INACTIVE_FIELD"),
                               (self.th.id, "DUPLICATE_FIELD"), (self.dia.id, "INVALID_VALUE")])

    def test_unknown_beats_not_applicable_beats_inactive_beats_invalid(self):
        # an inactive field with an invalid value reports INACTIVE_FIELD (first failure wins)
        self.assertEqual(self.reasons([{"field_id": self.off.id, "value": 5}]), [(self.off.id, "INACTIVE_FIELD")])
        self.assertEqual(self.reasons([{"field_id": self.other.id, "value": 5}]), [(self.other.id, "NOT_APPLICABLE")])

    def test_structure_errors_are_VALIDATION_ERROR(self):
        for bad_in in ["x", {}, [{"field_id": self.th.id}], [{"value": "1"}], [5],
                       [{"field_id": self.th.id, "value": "1", "field_code": "THICKNESS"}],       # client may not author the snapshot
                       [{"field_id": self.th.id, "value": "1", "data_type": "DECIMAL"}],
                       [{"field_id": "not-a-uuid", "value": "1"}], [{"field_id": 7, "value": "1"}]]:
            with self.assertRaises(AppError) as c:
                self.build(bad_in)
            self.assertEqual(c.exception.code, ErrorCode.VALIDATION_ERROR, bad_in)

    def test_null_value_invalid(self):
        self.assertEqual(self.reasons([{"field_id": self.th.id, "value": None}]), [(self.th.id, "INVALID_VALUE")])

    def test_snapshot_is_a_copy_not_a_reference(self):
        s = self.build([{"field_id": self.dia.id, "value": "2"}])
        self.fields[self.dia.id] = FieldDef(**{**self.dia.__dict__, "name": "Renamed", "options": ("9",)})
        self.assertEqual(s[0]["field_name"], "Dia" + "meter")      # later field edits never alter a stored snapshot

    def test_missing_required(self):
        s = self.build([{"field_id": self.th.id, "value": "1"}])
        self.assertEqual(missing_required([self.dia.id], s), [self.dia.id])
        s2 = self.build([{"field_id": self.dia.id, "value": "1"}])
        self.assertEqual(missing_required([self.dia.id], s2), [])


@unittest.skipUnless(pg.available() and SQL_DIR, "SKIPPED: needs PostgreSQL via psql and TF_SQL_DIR (folder with 001/002/003/998)")
class AcceptedByTheRealDatabaseTrigger(unittest.TestCase):
    """The snapshot must be exactly what trigger trg_request_items_validate_specifications (002) accepts."""
    DB = "tf_core_specs"

    @classmethod
    def setUpClass(cls):
        pg.make_db(cls.DB, SQL_DIR)
        rc, out, e = pg.psql(cls.DB, """
          SELECT o.id, p.id, u.id, c.id, usr.id FROM organizations o
            JOIN products p ON p.organization_id=o.id AND p.code='GAS-PIPE-2IN'
            JOIN units u ON u.organization_id=o.id AND u.code='KG'
            JOIN customers c ON c.organization_id=o.id
            JOIN users usr ON usr.organization_id=o.id AND usr.username='admin' WHERE o.code='DEMO'""")
        assert rc == 0, e
        cls.org, cls.prod, cls.unit, cls.cust, cls.admin = out.strip().split("|")
        rc, out, e = pg.psql(cls.DB, f"""
          SELECT f.id, f.code, f.name, f.data_type FROM product_specification_fields f
          WHERE f.organization_id='{cls.org}' ORDER BY f.display_order""")
        cls.db_fields = [l.split("|") for l in out.strip().splitlines()]
        rc, out, e = pg.psql(cls.DB, f"""
          INSERT INTO purchase_requests (organization_id, request_number, customer_id, created_by, updated_by)
          VALUES ('{cls.org}', '1405-000001', '{cls.cust}', '{cls.admin}', '{cls.admin}') RETURNING id""")
        assert rc == 0, e
        cls.req = out.strip().splitlines()[0]

    def insert_item(self, snapshot):
        js = json.dumps(snapshot, ensure_ascii=False).replace("'", "''")
        return pg.psql(self.DB, f"""INSERT INTO purchase_request_items
            (organization_id, purchase_request_id, product_id, unit_id, quantity, specifications)
            VALUES ('{self.org}','{self.req}','{self.prod}','{self.unit}', 1, '{js}'::jsonb)""")

    def test_snapshot_built_from_database_fields_is_accepted(self):
        fields = {}
        for fid, code, name, dt in self.db_fields:
            rc, out, e = pg.psql(self.DB, f"SELECT is_active, is_required, coalesce(options::text,'') FROM product_specification_fields WHERE id='{fid}'")
            act, req, opts = out.strip().split("|")
            fields[fid] = FieldDef(fid, code, name, dt, act == "t", req == "t", tuple(json.loads(opts)) if opts else None)
        by = {f.code: f for f in fields.values()}
        snap = build_snapshot([{"field_id": by["DIAMETER"].id, "value": "2"},
                               {"field_id": by["THICKNESS_MM"].id, "value": "۲٫۵۰"},
                               {"field_id": by["GRADE"].id, "value": " St37 "}], fields, list(fields))
        rc, out, e = self.insert_item(snap)
        self.assertEqual(rc, 0, e)
        # and the database refuses the shapes the Service must never produce
        broken = dict(snap[0]); broken["data_type"] = "text"                      # lower-case type
        self.assertNotEqual(self.insert_item([broken])[0], 0)
        broken = dict(snap[0]); broken["field_id"] = 7                            # integer id
        self.assertNotEqual(self.insert_item([broken])[0], 0)
        self.assertNotEqual(self.insert_item([snap[0], snap[0]])[0], 0)           # duplicate field


if __name__ == "__main__":
    unittest.main()
