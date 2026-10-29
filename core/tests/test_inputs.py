import os, random, unittest
from datetime import date
from decimal import Decimal
from tradeflow_core import customers, inputs, purchase_inputs as pi, auth_inputs as ai
from tradeflow_core.errors import AppError, ErrorCode
from tests import pg

SQL_DIR = os.environ.get("TF_SQL_DIR")
TODAY = date(2026, 10, 16)
U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"


def reasons(fn, *a):
    try:
        fn(*a)
    except AppError as e:
        assert e.code.name in ('VALIDATION_ERROR','INVALID_MONEY','INVALID_QUANTITY','AMOUNT_OUT_OF_RANGE'), e.code
        return {(d["field"], d["reason"]) for d in e.details}
    raise AssertionError("no error raised")


class Common(unittest.TestCase):
    def test_strict_object(self):
        self.assertIn(("organization_id", "NOT_ALLOWED"), reasons(inputs.strict_object, {"organization_id": 1}, ["a"]))
        self.assertIn(("zzz", "UNKNOWN_FIELD"), reasons(inputs.strict_object, {"zzz": 1}, ["a"]))
        self.assertIn(("a", "REQUIRED"), reasons(lambda b: inputs.strict_object(b, ["a"], required=["a"]), {}))
        self.assertIn(("$", "MUST_BE_OBJECT"), reasons(inputs.strict_object, [], ["a"]))

    def test_text_uuid_pagination(self):
        self.assertIsNone(inputs.text("   ", "f", 5))
        self.assertEqual(inputs.text(" ab ", "f", 5), "ab")
        self.assertIn(("f", "MAX_LENGTH_3"), reasons(inputs.text, "abcd", "f", 3))
        self.assertIn(("f", "MUST_BE_STRING"), reasons(inputs.text, 5, "f", 3))
        self.assertEqual(inputs.parse_uuid(U1, "x"), U1)
        for bad in ("nope", 5, None, U1.replace("-", "")):
            self.assertIn(("x", "NOT_A_UUID"), reasons(inputs.parse_uuid, bad, "x"))
        self.assertEqual(inputs.parse_uuid("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", "x"), "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")  # canonical lower-case
        self.assertEqual(inputs.parse_pagination(), (1, 50))
        self.assertEqual(inputs.parse_pagination("2", "200"), (2, 200))
        for p, s in (("0", None), ("-1", None), (None, "201"), (None, "0"), ("a", None), ("1.5", None), (None, "")):
            reasons(inputs.parse_pagination, p, s)


class Customers(unittest.TestCase):
    def test_create_defaults_and_rules(self):
        c = customers.parse_create({"customer_type": "COMPANY", "name": " شرکت ", "national_id": "۱۲ ۳۴"})
        self.assertEqual((c["name"], c["national_id"], c["credit_limit"], c["is_active"]), ("شرکت", "1234", 0, True))
        self.assertIsNone(c["email"])
        reasons(customers.parse_create, {"name": "x"})
        reasons(customers.parse_create, {"customer_type": "X", "name": "x"})
        reasons(customers.parse_create, {"customer_type": "COMPANY", "name": "  "})
        reasons(customers.parse_create, {"customer_type": "COMPANY", "name": "x", "credit_limit": "-1"})
        reasons(customers.parse_create, {"customer_type": "COMPANY", "name": "x", "is_active": "true"})
        reasons(customers.parse_create, {"customer_type": "COMPANY", "name": "x", "mobile": "1" * 31})
        reasons(customers.parse_create, {"customer_type": "COMPANY", "name": "x", "id": U1})

    def test_patch_requires_updated_at(self):
        ch, ts = customers.parse_patch({"name": "n", "updated_at": "T"})
        self.assertEqual((ch, ts), ({"name": "n"}, "T"))
        reasons(customers.parse_patch, {"name": "n"})

    def test_search(self):
        self.assertIsNone(customers.search_terms(" "))
        self.assertEqual(customers.search_terms("AbC ۱۲")["identifier"], "AbC12")


@unittest.skipUnless(pg.available() and SQL_DIR, "SKIPPED: needs PostgreSQL via psql and TF_SQL_DIR")
class NormalizeIdentifierOracle(unittest.TestCase):
    def test_mirror_equals_real_function(self):
        pg.make_db("tf_core_inp", SQL_DIR)
        rnd = random.Random(7)
        alphabet = list("abcXYZ0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩ -_./\t\n") + ["‌", "‎", "‏", " ", " ", "ی", "ک", " "]
        cases = ["", " ", None, "‌", "۰۱۲", "a b", "x y"] + ["".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 14))) for _ in range(1500)]
        # one round trip: JSON-encoded, compared exactly (NULL vs '' kept distinct)
        import json
        payload = json.dumps(cases).replace("'", "''")
        rc, out, e = pg.psql("tf_core_inp", f"""
          SELECT i, coalesce(normalize_identifier(v), '<NULL>') FROM jsonb_array_elements_text('{payload}'::jsonb) WITH ORDINALITY AS t(v,i)""")
        # jsonb_array_elements_text turns JSON null into SQL NULL
        self.assertEqual(rc, 0, e)
        got = {}
        # rows may contain newlines in output only for NULL placeholder / normalized strings (whitespace removed) -> safe
        for line in out.splitlines():
            i, _, v = line.partition("|")
            got[int(i)] = v
        self.assertEqual(len(got), len(cases))
        bad = [(c, got[i + 1]) for i, c in enumerate(cases)
               if (customers.normalize_identifier(c) if c is not None else "<NULL>") != got[i + 1]
               and not (customers.normalize_identifier(c) is None and got[i + 1] == "<NULL>")]
        self.assertEqual(bad, [], bad[:5])


class Purchase(unittest.TestCase):
    def test_delivery_date(self):
        f = pi.parse_delivery_date
        self.assertEqual(f("۲۰۲۶-۱۰-۱۶", TODAY), TODAY)
        self.assertIsNone(f(None, TODAY)); self.assertIsNone(f(" ", TODAY))
        self.assertIn(("requested_delivery_date", "BEFORE_TODAY"), reasons(f, "2026-10-15", TODAY))
        for bad in ("2026-02-30", "2026/10/16", "26-10-16", "x", "2026-13-01"):
            self.assertIn(("requested_delivery_date", "INVALID_DATE"), reasons(f, bad, TODAY))
        reasons(f, 5, TODAY)

    def test_request_create(self):
        r = pi.parse_request_create({"customer_id": U1, "items": [{"product_id": U2, "quantity": "۱۲.۵"}]}, TODAY)
        it = r["items"][0]
        self.assertEqual(it["quantity"], Decimal("12.5"))
        self.assertNotIn("unit_id", it)
        self.assertEqual((it["unit_price"], it["bundle_count"], it["specifications"]), (0, 0, []))
        for body in ({}, {"customer_id": U1, "status": "SUBMITTED"}, {"customer_id": U1, "request_number": "x"},
                     {"customer_id": U1, "items": "x"}, {"customer_id": U1, "items": [{"quantity": "1"}]},
                     {"customer_id": U1, "items": [{"product_id": U2, "quantity": "1", "line_total": "5"}]}):
            reasons(pi.parse_request_create, body, TODAY)

    def test_item_patch_subset_and_pricing(self):
        ch, ts = pi.parse_item_patch({"quantity": "2", "updated_at": "T"})
        self.assertEqual((ch, ts), ({"quantity": Decimal("2")}, "T"))
        reasons(pi.parse_item_patch, {"quantity": "2"})
        reasons(pi.parse_item_patch, {"specifications": {}, "updated_at": "T"})
        lines, ts = pi.parse_pricing({"updated_at": "T", "lines": [{"item_id": U1, "unit_price": "100"}]})
        self.assertEqual(lines, [{"item_id": U1, "unit_price": 100}])
        for body in ({"updated_at": "T", "lines": []}, {"updated_at": "T", "lines": [{"item_id": U1}]},
                     {"updated_at": "T", "lines": [{"item_id": U1, "unit_price": "1"}, {"item_id": U1, "tax_amount": "1"}]},
                     {"updated_at": "T", "lines": [{"item_id": U1, "unit_price": "1.5"}]}, {"lines": []}):
            reasons(pi.parse_pricing, body)

    def test_date_param(self):
        self.assertEqual(pi.parse_date_param("۲۰۲۴-۰۱-۰۲", "created_from"), date(2024, 1, 2))
        self.assertIsNone(pi.parse_date_param(None, "x"))
        for bad in ("2024-1-2", "2024-02-30", "x", ""):
            reasons(pi.parse_date_param, bad, "created_from")

    def test_cancel(self):
        self.assertEqual(pi.parse_cancel({"reason": " دلیل "}), "دلیل")
        reasons(pi.parse_cancel, {}); 
        with self.assertRaises(AppError): pi.parse_cancel({"reason": "  "})


class Login(unittest.TestCase):
    def test_login(self):
        self.assertEqual(ai.parse_login({"organization_code": " demo ", "username": " Admin ", "password": " p "}), ("DEMO", "admin", " p "))
        self.assertEqual(ai.parse_login({"organization_code": "ORG-۰۰۰۰۰۱", "username": "a", "password": "x"})[0], "ORG-000001")
        for b in ({}, {"organization_code": "", "username": "a", "password": "x"}, {"organization_code": "D", "username": "a", "password": ""},
                  {"organization_code": "D", "username": "a", "password": "x" * 1025}, {"organization_code": 1, "username": "a", "password": "x"},
                  {"organization_code": "D", "username": "a", "password": "x", "role": "ADMIN"}):
            reasons(ai.parse_login, b)
        self.assertEqual(ai.parse_refresh_body({"refresh_token": "abc"}), "abc")
        reasons(ai.parse_refresh_body, {"refresh_token": ""})


if __name__ == "__main__":
    unittest.main()


class Products(unittest.TestCase):
    def test_product_inputs(self):
        from tradeflow_core import products as pr
        p = pr.parse_create({"code": " A-1 ", "name": "n", "category_id": U1, "default_unit_id": U2})
        self.assertEqual((p["code"], p["description"], p["is_active"]), ("A-1", None, True))
        for b in ({}, {"code": "", "name": "n", "category_id": U1, "default_unit_id": U2},
                  {"code": "c" * 101, "name": "n", "category_id": U1, "default_unit_id": U2},
                  {"code": "c", "name": "n", "category_id": "x", "default_unit_id": U2},
                  {"code": "c", "name": "n", "category_id": U1, "default_unit_id": U2, "organization_id": U1}):
            reasons(pr.parse_create, b)
        self.assertEqual(pr.parse_patch({"is_active": False, "updated_at": "T"}), ({"is_active": False}, "T"))
        reasons(pr.parse_patch, {"is_active": "no", "updated_at": "T"})
        self.assertIsNone(pr.parse_bool_filter(None)); self.assertIs(pr.parse_bool_filter("True"), True)
        reasons(pr.parse_bool_filter, "1")
        self.assertEqual(pr.parse_unit_type_filter("WEIGHT"), "WEIGHT"); reasons(pr.parse_unit_type_filter, "KG")


class Config(unittest.TestCase):
    def test_config(self):
        from tradeflow_core import config
        s, w = config.load({"TRADEFLOW_JWT_SECRET": "x" * 32})
        self.assertEqual((s.access_ttl_seconds, s.refresh_grace_seconds, s.workers, w), (3600, 10, 1, []))
        self.assertTrue(config.load({"TRADEFLOW_JWT_SECRET": "x" * 32, "WORKERS": "4"})[1])
        for env in ({}, {"TRADEFLOW_JWT_SECRET": "short"}, {"TRADEFLOW_JWT_SECRET": "x" * 32, "TRADEFLOW_ENV": "prod"},
                    {"TRADEFLOW_JWT_SECRET": "x" * 32, "TRADEFLOW_REFRESH_GRACE_SECONDS": "-1"},
                    {"TRADEFLOW_JWT_SECRET": "dev" + "x" * 40, "TRADEFLOW_ENV": "production"}):
            with self.assertRaises(config.ConfigError):
                config.load(env)
