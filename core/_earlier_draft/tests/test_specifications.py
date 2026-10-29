import json
import unittest
import uuid

from tradeflow_core.errors import AppError
from tradeflow_core.specifications import FieldDef, build_snapshot, canonicalize_value, missing_required, _Invalid
from . import pg

U = lambda: str(uuid.uuid4())


def F(dt, **kw):
    return FieldDef(id=U(), code=kw.pop("code", dt), name=kw.pop("name", "نام " + dt), data_type=dt, **kw)


def ok(field, value):
    return canonicalize_value(field, value)


def bad(field, value):
    with unittest.TestCase().assertRaises(_Invalid):
        canonicalize_value(field, value)


class ValueRules(unittest.TestCase):
    """Every case listed at the end of contract section 12."""

    def test_decimal(self):
        f = F("DECIMAL")
        self.assertEqual(ok(f, "125.50"), "125.5")
        self.assertEqual(ok(f, "2.50"), "2.5")
        self.assertEqual(ok(f, "3.0"), "3")
        self.assertEqual(ok(f, "007.10"), "7.1")
        self.assertEqual(ok(f, "-0.0"), "0")
        self.assertEqual(ok(f, "-2.5"), "-2.5")
        self.assertEqual(ok(f, "۲٫۵۰"), "2.5")                  # Persian digits + Arabic decimal separator
        self.assertEqual(ok(f, "999999999999.999999"), "999999999999.999999")   # 12 + 6 digits
        for v in ["ABC", "1,5", "", "1.", ".5", "1e3", "1.1234567", "1" * 13, 2.5, 3, True, None, ["1"]]:
            bad(f, v)

    def test_number(self):
        f = F("NUMBER")
        self.assertEqual(ok(f, "10"), "10")
        self.assertEqual(ok(f, "۱۰"), "10")
        self.assertEqual(ok(f, "-0"), "0")
        self.assertEqual(ok(f, "-007"), "-7")
        self.assertEqual(ok(f, "9" * 18), "9" * 18)
        for v in ["10.5", "1" * 19, "x", "", 10, 10.0, True, None]:
            bad(f, v)

    def test_boolean(self):
        f = F("BOOLEAN")
        self.assertIs(ok(f, True), True)
        self.assertIs(ok(f, False), False)
        for v in ["true", "false", "1", 1, 0, None, "yes"]:
            bad(f, v)

    def test_date(self):
        f = F("DATE")
        self.assertEqual(ok(f, "2026-10-08"), "2026-10-08")
        self.assertEqual(ok(f, "۲۰۲۶-۱۰-۰۸"), "2026-10-08")
        self.assertEqual(ok(f, "2028-02-29"), "2028-02-29")
        for v in ["2026-02-30", "2027-02-29", "2026-13-01", "2026-1-1", "20261008", "1405-07-16x", "", 20261008]:
            bad(f, v)

    def test_select(self):
        f = F("SELECT", options=("A", "B"))
        self.assertEqual(ok(f, "A"), "A")
        for v in ["C", "a", " A", "", ["A"], None, 1]:
            bad(f, v)
        bad(F("SELECT", options=None), "A")

    def test_multi_select(self):
        f = F("MULTI_SELECT", options=("A", "B", "C"))
        self.assertEqual(ok(f, ["C", "A"]), ["A", "C"])         # order of the field's options
        for v in [[], ["A", "A"], ["A", "Z"], "A", [1], None, ["A", None]]:
            bad(f, v)

    def test_text(self):
        f = F("TEXT")
        self.assertEqual(ok(f, "  گرید ۱۲ "), "گرید ۱۲")           # trimmed; digits inside free text untouched
        self.assertEqual(ok(f, "x" * 1000), "x" * 1000)
        for v in ["", "   ", "x" * 1001, 5, None, ["a"]]:
            bad(f, v)


class Snapshot(unittest.TestCase):
    def setUp(self):
        self.dia = F("SELECT", code="DIAMETER", name="قطر", options=("1", "2"), is_required=True)
        self.th = F("DECIMAL", code="THICKNESS", name="ضخامت")
        self.old = F("TEXT", code="OLD", is_active=False)
        self.other_cat = F("TEXT", code="ELSEWHERE")
        self.fields = {x.id: x for x in (self.dia, self.th, self.old, self.other_cat)}
        self.applicable = [self.dia.id, self.th.id, self.old.id]

    def build(self, items):
        return build_snapshot(items, self.fields, self.applicable)

    def reasons(self, items):
        try:
            self.build(items)
        except AppError as e:
            return e.code, [(d.get("reason")) for d in e.details]
        self.fail("no error")

    def test_snapshot_shape_and_order(self):
        snap = self.build([{"field_id": self.th.id, "value": "2.50"}, {"field_id": self.dia.id, "value": "2"}])
        self.assertEqual(snap, [
            {"field_id": self.th.id, "field_code": "THICKNESS", "field_name": "ضخامت", "data_type": "DECIMAL", "value": "2.5"},
            {"field_id": self.dia.id, "field_code": "DIAMETER", "field_name": "قطر", "data_type": "SELECT", "value": "2"}])
        self.assertEqual(self.build([]), [])
        self.assertEqual(self.build(None), [])

    def test_reasons_in_contract_order(self):
        self.assertEqual(self.reasons([{"field_id": U(), "value": "x"}]), ("SPECIFICATION_INVALID", ["UNKNOWN_FIELD"]))
        self.assertEqual(self.reasons([{"field_id": self.other_cat.id, "value": "x"}])[1], ["NOT_APPLICABLE"])
        self.assertEqual(self.reasons([{"field_id": self.old.id, "value": "x"}])[1], ["INACTIVE_FIELD"])
        self.assertEqual(self.reasons([{"field_id": self.th.id, "value": "1"}, {"field_id": self.th.id, "value": "2"}])[1], ["DUPLICATE_FIELD"])
        self.assertEqual(self.reasons([{"field_id": self.th.id, "value": "ABC"}])[1], ["INVALID_VALUE"])
        # an unknown AND not-applicable id: unknown wins; an inactive field of another category: not-applicable wins
        self.assertEqual(self.reasons([{"field_id": U(), "value": 1}])[1], ["UNKNOWN_FIELD"])

    def test_all_failing_elements_reported_with_ids(self):
        with self.assertRaises(AppError) as cm:
            self.build([{"field_id": self.th.id, "value": "ABC"}, {"field_id": U(), "value": "x"}])
        self.assertEqual([d["reason"] for d in cm.exception.details], ["INVALID_VALUE", "UNKNOWN_FIELD"])
        self.assertEqual(cm.exception.http_status, 422)

    def test_field_of_another_org_equals_unknown(self):
        foreign = U()          # not in `fields`: exactly what another organization's field looks like to this org
        a = self.reasons([{"field_id": foreign, "value": "x"}])
        b = self.reasons([{"field_id": U(), "value": "x"}])
        self.assertEqual(a, b)

    def test_client_cannot_author_snapshot_keys(self):
        for el in [{"field_id": self.th.id, "value": "1", "field_code": "X"},
                   {"field_id": self.th.id, "value": "1", "data_type": "TEXT"},
                   {"field_id": self.th.id}, {"value": "1"}, "x", 5]:
            with self.assertRaises(AppError) as cm:
                self.build([el])
            self.assertEqual(cm.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(AppError):
            self.build({"field_id": self.th.id, "value": "1"})               # not an array
        with self.assertRaises(AppError):
            self.build([{"field_id": "not-a-uuid", "value": "1"}])

    def test_null_value_is_invalid(self):
        self.assertEqual(self.reasons([{"field_id": self.th.id, "value": None}])[1], ["INVALID_VALUE"])

    def test_uppercase_uuid_resolves(self):
        snap = self.build([{"field_id": self.dia.id.upper(), "value": "1"}])
        self.assertEqual(snap[0]["field_id"], self.dia.id)

    def test_snapshot_is_independent_of_later_field_changes(self):
        snap = self.build([{"field_id": self.dia.id, "value": "2"}])
        frozen = json.dumps(snap, sort_keys=True)
        self.fields[self.dia.id] = FieldDef(self.dia.id, "RENAMED", "نام جدید", "SELECT", ("9",), True, True)
        self.assertEqual(json.dumps(snap, sort_keys=True), frozen)

    def test_missing_required_at_submit(self):
        snap = self.build([{"field_id": self.th.id, "value": "1"}])
        self.assertEqual(missing_required(snap, [self.dia.id]), [self.dia.id])
        snap = self.build([{"field_id": self.dia.id, "value": "1"}])
        self.assertEqual(missing_required(snap, [self.dia.id]), [])


@unittest.skipUnless(pg.available(), "PostgreSQL (psql) not available")
class SnapshotVsDatabaseTrigger(unittest.TestCase):
    """The snapshot built from the REAL seeded fields is accepted by the real trigger of migration 002."""

    @classmethod
    def setUpClass(cls):
        cls.db = pg.make_db("tf_core_spec")
        rows = pg.psql(cls.db, """select f.id, f.code, f.name, f.data_type, coalesce(f.options::text,''), f.is_active, f.is_required
                                  from product_specification_fields f order by f.display_order""").splitlines()
        cls.fields = {}
        for r in rows:
            i, code, name, dt, opts, act, req = r.split("|")
            cls.fields[i] = FieldDef(i, code, name, dt, tuple(json.loads(opts)) if opts else None, act == "t", req == "t")
        cls.org = pg.psql(cls.db, "select id from organizations where code='DEMO'")
        uid = pg.psql(cls.db, "select id from users where username='admin'")
        cust = pg.psql(cls.db, "select id from customers limit 1")
        cls.prod = pg.psql(cls.db, "select id from products limit 1")
        cls.unit = pg.psql(cls.db, "select id from units where code='KG'")
        pg.psql(cls.db, f"""insert into purchase_requests(id,organization_id,request_number,customer_id,created_by)
             values ('00000000-0000-0000-0000-0000000000b1','{cls.org}','S-1','{cust}','{uid}')""")

    def insert(self, snap):
        s = json.dumps(snap, ensure_ascii=False).replace("'", "''")
        return pg.psql(self.db, f"""insert into purchase_request_items(organization_id,purchase_request_id,product_id,unit_id,quantity,specifications)
             values ('{self.org}','00000000-0000-0000-0000-0000000000b1','{self.prod}','{self.unit}',1,'{s}'::jsonb) returning specifications""")

    def test_seed_fields_are_what_the_contract_expects(self):
        self.assertEqual(sorted(f.data_type for f in self.fields.values()), ["DECIMAL", "SELECT", "TEXT"])

    def test_service_snapshot_is_accepted_and_stored_verbatim(self):
        by = {f.code: f for f in self.fields.values()}
        snap = build_snapshot([{"field_id": by["DIAMETER"].id, "value": "2"},
                               {"field_id": by["THICKNESS_MM"].id, "value": "۲٫۵۰"},
                               {"field_id": by["GRADE"].id, "value": " St37 "}],
                              self.fields, self.fields.keys())
        stored = json.loads(self.insert(snap).splitlines()[0])
        self.assertEqual(stored, snap)

    def test_trigger_rejects_what_the_service_would_never_build(self):
        by = {f.code: f for f in self.fields.values()}
        good = {"field_id": by["GRADE"].id, "field_code": "GRADE", "field_name": "x", "data_type": "TEXT", "value": "a"}
        for broken, state in [({**good, "data_type": "NUMBER"}, "23503"), ({**good, "field_code": "NOPE"}, "23503"),
                              ({k: v for k, v in good.items() if k != "value"}, "23514")]:
            with self.assertRaises(pg.PgError) as cm:
                self.insert([broken])
            self.assertEqual(cm.exception.sqlstate, state)
