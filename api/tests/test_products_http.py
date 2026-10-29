import unittest
import uuid

from fastapi.testclient import TestClient

from tests import support

P = "/api/v1/products"


def uniq(prefix="p"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def err(r):
    e = dict(r.json()["error"])
    e.pop("request_id")
    return e


@unittest.skipUnless(support.ready(), "SKIPPED: needs PostgreSQL (psql) and TF_SQL_DIR")
class ProductsHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.build_db()
        cls.c = TestClient(support.make_app())
        cls.admin, cls.sales, cls.acct, cls.other = (support.headers("admin"), support.headers("sales"),
                                                     support.headers("accounting"), support.headers("admin", "OTHER"))
        q = lambda sql: support.scalar(sql)
        cls.cat = q("SELECT id FROM product_categories WHERE code = 'PIPE_PROFILE'")
        cls.kg = q("SELECT id FROM units WHERE code = 'KG' AND organization_id = (SELECT id FROM organizations WHERE code = 'DEMO')")
        cls.demo_product = q("SELECT id FROM products WHERE code = 'GAS-PIPE-2IN'")
        cls.b_cat = q("SELECT id FROM product_categories WHERE code = 'BCAT'")
        cls.b_unit = q("SELECT id FROM units WHERE code = 'BKG'")
        cls.b_product = q("SELECT id FROM products WHERE code = 'B-PROD'")
        # an inactive category/unit and a category without any specification template, in the demo organization
        support.scalar("INSERT INTO product_categories (organization_id, name, code, is_active) SELECT id, 'غیرفعال', 'OLD_CAT', FALSE FROM organizations WHERE code = 'DEMO' ON CONFLICT DO NOTHING")
        support.scalar("INSERT INTO product_categories (organization_id, name, code) SELECT id, 'بدون مشخصات', 'NO_SPEC' FROM organizations WHERE code = 'DEMO' ON CONFLICT DO NOTHING")
        support.scalar("INSERT INTO units (organization_id, name, code, unit_type, is_active) SELECT id, 'قدیمی', 'OLDU', 'LENGTH', FALSE FROM organizations WHERE code = 'DEMO' ON CONFLICT DO NOTHING")
        cls.old_cat = q("SELECT id FROM product_categories WHERE code = 'OLD_CAT'")
        cls.nospec_cat = q("SELECT id FROM product_categories WHERE code = 'NO_SPEC'")
        cls.old_unit = q("SELECT id FROM units WHERE code = 'OLDU'")

    def body(self, **kw):
        return {"code": uniq("C"), "name": uniq("N"), "category_id": self.cat, "default_unit_id": self.kg, **kw}

    def create(self, **kw):
        r = self.c.post(P, json=self.body(**kw), headers=self.admin)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]

    def test_create_shape_get_and_roles(self):
        d = self.create(description="d")
        self.assertEqual((d["category"]["code"], d["default_unit"]["code"], d["default_unit"]["unit_type"], d["is_active"]), ("PIPE_PROFILE", "KG", "WEIGHT", True))
        self.assertEqual(self.c.get(f"{P}/{d['id']}", headers=self.acct).json()["data"], d)
        for h in (self.sales, self.acct):
            r = self.c.post(P, json=self.body(), headers=h)
            self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
        r = self.c.patch(f"{P}/{d['id']}", json={"name": "x", "updated_at": d["updated_at"]}, headers=self.sales)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))

    def test_duplicates(self):
        d = self.create()
        r = self.c.post(P, json=self.body(code=d["code"]), headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]), (409, "DUPLICATE_RESOURCE", {"field": "code"}))
        r = self.c.post(P, json=self.body(name=d["name"]), headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]), (409, "DUPLICATE_RESOURCE", {"field": "name"}))

    def test_references(self):
        r = self.c.post(P, json=self.body(category_id=self.old_cat), headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "INACTIVE_REFERENCE"))
        r = self.c.post(P, json=self.body(default_unit_id=self.old_unit), headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "INACTIVE_REFERENCE"))
        # T-TENANT (b): another organization's id and a random id are indistinguishable
        other = self.c.post(P, json=self.body(category_id=self.b_cat), headers=self.admin)
        ghost = self.c.post(P, json=self.body(category_id=str(uuid.uuid4())), headers=self.admin)
        self.assertEqual((other.status_code, err(other)), (422, err(ghost)))
        self.assertEqual(err(other)["code"], "REFERENCE_NOT_FOUND")
        o2 = self.c.post(P, json=self.body(default_unit_id=self.b_unit), headers=self.admin)
        g2 = self.c.post(P, json=self.body(default_unit_id=str(uuid.uuid4())), headers=self.admin)
        self.assertEqual((o2.status_code, err(o2)), (422, err(g2)))
        for bad in ({"category_id": "x"}, {"organization_id": self.cat}, {"code": ""}):
            self.assertEqual(self.c.post(P, json=self.body(**bad), headers=self.admin).status_code, 422, bad)

    def test_list_filters(self):
        tag = uniq("flt")
        a = self.create(name=f"{tag}-b")
        b = self.create(name=f"{tag}-a", category_id=self.nospec_cat)
        r = self.c.get(P, params={"search": tag}, headers=self.admin).json()
        self.assertEqual(([i["id"] for i in r["items"]], r["total"]), ([b["id"], a["id"]], 2))
        r = self.c.get(P, params={"search": tag, "category_id": self.nospec_cat}, headers=self.admin).json()
        self.assertEqual([i["id"] for i in r["items"]], [b["id"]])
        self.c.patch(f"{P}/{a['id']}", json={"is_active": False, "updated_at": a["updated_at"]}, headers=self.admin)
        r = self.c.get(P, params={"search": tag, "is_active": "false"}, headers=self.admin).json()
        self.assertEqual([i["id"] for i in r["items"]], [a["id"]])
        ids = [i["id"] for i in self.c.get(P, params={"page_size": 200}, headers=self.other).json()["items"]]
        self.assertEqual(ids, [self.b_product])                                              # organization B sees only its own product

    def test_patch(self):
        d = self.create()
        r = self.c.patch(f"{P}/{d['id']}", json={"name": "renamed-" + uniq(), "category_id": self.nospec_cat, "updated_at": d["updated_at"]}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        new = r.json()["data"]
        self.assertEqual((new["category"]["code"], new["updated_at"] != d["updated_at"]), ("NO_SPEC", True))
        r = self.c.patch(f"{P}/{d['id']}", json={"name": "late", "updated_at": d["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]["current"]), (409, "STALE_UPDATE", new))
        r = self.c.patch(f"{P}/{d['id']}", json={"category_id": self.old_cat, "updated_at": new["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (422, "INACTIVE_REFERENCE"))
        r = self.c.patch(f"{P}/{d['id']}", json={"name": new["name"], "updated_at": new["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, r.json()["data"]["updated_at"]), (200, new["updated_at"]))      # no-op
        dup = self.create()
        r = self.c.patch(f"{P}/{d['id']}", json={"code": dup["code"], "updated_at": new["updated_at"]}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"]), (409, "DUPLICATE_RESOURCE"))

    def test_tenant_isolation(self):
        d = self.create()
        ghost = str(uuid.uuid4())
        for path in (f"{P}/{d['id']}", f"{P}/{d['id']}/specifications"):
            a = self.c.get(path, headers=self.other)
            b = self.c.get(path.replace(d["id"], ghost), headers=self.other)
            self.assertEqual((a.status_code, err(a)), (404, err(b)))
        self.assertEqual(err(self.c.get(f"{P}/{d['id']}", headers=self.other))["details"], {"resource": "product"})
        p1 = self.c.patch(f"{P}/{d['id']}", json={"name": "hack", "updated_at": d["updated_at"]}, headers=self.other)
        self.assertEqual(p1.status_code, 404)
        self.assertEqual(self.c.get(f"{P}/{self.b_product}", headers=self.admin).status_code, 404)

    def test_specifications(self):
        r = self.c.get(f"{P}/{self.demo_product}/specifications", headers=self.acct)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual(data["product_id"], self.demo_product)
        self.assertEqual([f["code"] for f in data["fields"]], ["DIAMETER", "THICKNESS_MM", "GRADE"])      # display_order ASC
        diameter, thickness, grade = data["fields"]
        self.assertEqual((diameter["data_type"], diameter["is_required"], diameter["options"], diameter["value"]), ("SELECT", True, ["1/2", "1", "2", "3"], "2"))
        self.assertEqual((thickness["data_type"], thickness["value"], grade["value"]), ("DECIMAL", None, None))
        self.assertEqual(set(diameter), {"field_id", "code", "name", "data_type", "is_required", "display_order", "options", "value"})
        d = self.create(category_id=self.nospec_cat)                                                       # no template -> nothing applicable
        r = self.c.get(f"{P}/{d['id']}/specifications", headers=self.admin)
        self.assertEqual(r.json()["data"]["fields"], [])

    def test_specification_value_forms(self):
        """Stored values of every data type come back in the canonical JSON forms of section 12."""
        tag = uniq("T").replace("-", "_")
        support.scalar(f"""
          INSERT INTO product_categories (organization_id, name, code) SELECT id, '{tag}', '{tag}' FROM organizations WHERE code = 'DEMO';
          INSERT INTO product_specification_templates (organization_id, category_id, name, code)
            SELECT c.organization_id, c.id, '{tag}', '{tag}' FROM product_categories c WHERE c.code = '{tag}';
          INSERT INTO product_specification_fields (organization_id, template_id, name, code, data_type, display_order, options)
            SELECT t.organization_id, t.id, v.c, v.c, v.t, v.o, v.opt::jsonb FROM product_specification_templates t
              CROSS JOIN (VALUES ('F1','TEXT',1,NULL),('F2','NUMBER',2,NULL),('F3','DECIMAL',3,NULL),('F4','BOOLEAN',4,NULL),
                                 ('F5','DATE',5,NULL),('F6','SELECT',6,'["a","b"]'),('F7','MULTI_SELECT',7,'["x","y","z"]'),
                                 ('F8','TEXT',8,NULL)) AS v(c,t,o,opt) WHERE t.code = '{tag}';""")
        cat = support.scalar(f"SELECT id FROM product_categories WHERE code = '{tag}'")
        org = support.scalar("SELECT id FROM organizations WHERE code = 'DEMO'")
        d = self.create(category_id=cat)
        support.scalar(f"""
          INSERT INTO product_specification_values (organization_id, product_id, field_id, value_text, value_number, value_decimal, value_boolean, value_date, value_option, value_options)
          SELECT '{org}', '{d['id']}', f.id,
                 CASE f.code WHEN 'F1' THEN 'متن' END, CASE f.code WHEN 'F2' THEN 42 END, CASE f.code WHEN 'F3' THEN 2.500000 END,
                 CASE f.code WHEN 'F4' THEN TRUE END, CASE f.code WHEN 'F5' THEN DATE '2026-10-23' END,
                 CASE f.code WHEN 'F6' THEN 'b' END, CASE f.code WHEN 'F7' THEN '["x","z"]'::jsonb END
            FROM product_specification_fields f JOIN product_specification_templates t ON t.id = f.template_id
           WHERE t.code = '{tag}' AND f.code <> 'F8';""")
        v = {f["code"]: f["value"] for f in self.c.get(f"{P}/{d['id']}/specifications", headers=self.admin).json()["data"]["fields"]}
        self.assertEqual(v, {"F1": "متن", "F2": "42", "F3": "2.5", "F4": True, "F5": "2026-10-23", "F6": "b", "F7": ["x", "z"], "F8": None})


if __name__ == "__main__":
    unittest.main()
