"""Shared fixtures: a real database built from the migrations + dev seed, and an app wired to it."""
import os
from datetime import datetime, timezone

from app.main import create_app
from app.settings import AppSettings
from tradeflow_core import config as core_config
from tradeflow_core.ratelimit import LoginRateLimiter
from tests import pg

SQL_DIR = os.environ.get("TF_SQL_DIR")
DB = "tf_api_test"
PASSWORD = "TradeFlow-Dev-1!"
SECRET = "test-secret-" + "x" * 40


def ready():
    return bool(SQL_DIR) and pg.available()


_READY = False
_TOKENS = {}

ORG_B_SQL = """
INSERT INTO organizations (code, name) VALUES ('OTHER', 'Other Org');
INSERT INTO roles (organization_id, code, name) SELECT id, 'ADMIN', 'Administrator' FROM organizations WHERE code = 'OTHER';
INSERT INTO users (organization_id, role_id, first_name, last_name, username, password_hash)
  SELECT o.id, r.id, 'B', 'Admin', 'admin', (SELECT password_hash FROM users WHERE username = 'admin' AND organization_id = (SELECT id FROM organizations WHERE code = 'DEMO'))
    FROM organizations o JOIN roles r ON r.organization_id = o.id AND r.code = 'ADMIN' WHERE o.code = 'OTHER';
INSERT INTO units (organization_id, name, code, unit_type) SELECT id, 'B-unit', 'BKG', 'WEIGHT' FROM organizations WHERE code = 'OTHER';
INSERT INTO product_categories (organization_id, name, code) SELECT id, 'B-category', 'BCAT' FROM organizations WHERE code = 'OTHER';
INSERT INTO products (organization_id, category_id, name, code, default_unit_id)
  SELECT o.id, c.id, 'B-product', 'B-PROD', u.id FROM organizations o
    JOIN product_categories c ON c.organization_id = o.id JOIN units u ON u.organization_id = o.id WHERE o.code = 'OTHER';
INSERT INTO customers (organization_id, customer_type, name) SELECT id, 'COMPANY', 'B-customer' FROM organizations WHERE code = 'OTHER';
"""


DEMO_EXTRA_SQL = """
-- a second SALES user (for ownership tests), same password as the seeded users
INSERT INTO users (organization_id, role_id, first_name, last_name, username, password_hash)
  SELECT u.organization_id, u.role_id, 'Sales', 'Two', 'sales2', u.password_hash FROM users u
   WHERE u.username = 'sales' AND u.organization_id = (SELECT id FROM organizations WHERE code = 'DEMO');
-- specification master data used by the request tests
INSERT INTO product_specification_fields (organization_id, template_id, name, code, data_type, is_active, display_order)
  SELECT t.organization_id, t.id, 'Inactive field', 'INACTIVE_F', 'TEXT', FALSE, 90 FROM product_specification_templates t
   WHERE t.code = 'PIPE_PROFILE_SPEC' AND t.organization_id = (SELECT id FROM organizations WHERE code = 'DEMO');
INSERT INTO product_categories (organization_id, name, code) SELECT id, 'Other category', 'OTHERCAT' FROM organizations WHERE code = 'DEMO';
INSERT INTO product_specification_templates (organization_id, category_id, name, code)
  SELECT c.organization_id, c.id, 'Other template', 'OTHER_TPL' FROM product_categories c WHERE c.code = 'OTHERCAT';
INSERT INTO product_specification_fields (organization_id, template_id, name, code, data_type)
  SELECT t.organization_id, t.id, 'Other field', 'OTHER_F', 'TEXT' FROM product_specification_templates t WHERE t.code = 'OTHER_TPL';
INSERT INTO product_specification_templates (organization_id, category_id, name, code)
  SELECT c.organization_id, c.id, 'B template', 'B_TPL' FROM product_categories c WHERE c.code = 'BCAT';
INSERT INTO product_specification_fields (organization_id, template_id, name, code, data_type)
  SELECT t.organization_id, t.id, 'B field', 'B_F', 'TEXT' FROM product_specification_templates t WHERE t.code = 'B_TPL';
"""


def build_db():
    """Build the database ONCE per test process (migrations 001-003 + seed 998) and add a second organization 'OTHER'."""
    global _READY
    if _READY:
        return
    pg.make_db(DB, SQL_DIR)
    for sql in (ORG_B_SQL, DEMO_EXTRA_SQL):
        rc, _, err = pg.psql(DB, sql)
        assert rc == 0, err
    _READY = True


def scalar(sql):
    rc, out, err = pg.psql(DB, sql)
    assert rc == 0, err
    return out.strip()


def headers(user="admin", org="DEMO"):
    """Authorization header for a seeded user; the login (argon2) is done once per user and cached for the process."""
    from fastapi.testclient import TestClient
    key = (org, user)
    if key not in _TOKENS:
        c = TestClient(make_app(limiter=LoginRateLimiter(max_failures=10_000)))
        r = c.post("/api/v1/auth/login", json=login_body(user, org=org))
        assert r.status_code == 200, r.text
        _TOKENS[key] = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
    return _TOKENS[key]


def make_app(limiter=None, clock=None, grace=10, pdf_renderer=None):
    core = core_config.Settings(SECRET, 3600, 30, grace, 1, "test")
    return create_app(AppSettings(core, f"dbname={DB}", ()), limiter=limiter or LoginRateLimiter(), clock=clock, pdf_renderer=pdf_renderer)


def login_body(user="admin", password=PASSWORD, org="DEMO"):
    return {"organization_code": org, "username": user, "password": password}
