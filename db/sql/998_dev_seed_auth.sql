-- Development seed only. Do not run in production (the runner refuses it).
-- TradeFlow 998_dev_seed_auth - contract D11.
--
-- Runs BEFORE the frozen 999 (seeds apply in numeric order), so it is self-sufficient: it creates the demo
-- organization (code DEMO) and everything 999 would create, with the SAME natural keys, then 999 inserts nothing.
-- Idempotent.  Dev login:  organization_code DEMO, username admin | sales | accounting, password  TradeFlow-Dev-1!
--
-- Same-name guard (evaluated first). The frozen 999 selects its target organization by NAME only, so:
--   * no organization named 'TradeFlow Demo'                      -> create it (national_id DEMO-NATIONAL-ID, code DEMO)
--   * exactly one, with national_id = 'DEMO-NATIONAL-ID', code DEMO -> use it
--   * anything else (real org sharing the name, several, wrong code) -> RAISE, change nothing
-- Passwords: an existing user 'admin' is upgraded ONLY if its hash is still exactly TEMPORARY_PASSWORD_HASH.

DO $$
DECLARE
    n INTEGER;
    r RECORD;
BEGIN
    SELECT count(*) INTO n FROM organizations WHERE name = 'TradeFlow Demo';
    IF n = 0 THEN
        RETURN;
    ELSIF n > 1 THEN
        RAISE EXCEPTION '998: % organizations are named ''TradeFlow Demo''; refusing to seed (frozen 999 selects by name)', n
            USING ERRCODE = '55000';
    END IF;
    SELECT national_id, code INTO r FROM organizations WHERE name = 'TradeFlow Demo';
    IF r.national_id IS DISTINCT FROM 'DEMO-NATIONAL-ID' THEN
        RAISE EXCEPTION '998: an organization named ''TradeFlow Demo'' exists but is not the demo organization (national_id differs); refusing to seed'
            USING ERRCODE = '55000';
    END IF;
    IF r.code IS DISTINCT FROM 'DEMO' THEN
        RAISE EXCEPTION '998: the demo organization has code %, expected DEMO (codes are immutable; fix by hand)', r.code
            USING ERRCODE = '55000';
    END IF;
END $$;

INSERT INTO organizations (name, legal_name, national_id, economic_code, registration_number,
                           phone, email, address, postal_code, code)
SELECT 'TradeFlow Demo', 'TradeFlow Demo Company', 'DEMO-NATIONAL-ID', 'DEMO-ECONOMIC-CODE', 'DEMO-REG',
       '02100000000', 'demo@tradeflow.local', 'Demo Address', '0000000000', 'DEMO'
WHERE NOT EXISTS (SELECT 1 FROM organizations WHERE name = 'TradeFlow Demo');

INSERT INTO roles (organization_id, code, name, description)
SELECT o.id, v.code, v.name, v.description
FROM (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o
CROSS JOIN (VALUES
  ('ADMIN',      'Administrator', 'Full access to organization data and settings'),
  ('SALES',      'Sales',         'Sales and customer management'),
  ('ACCOUNTING', 'Accounting',    'Financial and accounting operations')
) AS v(code, name, description)
WHERE NOT EXISTS (SELECT 1 FROM roles r WHERE r.organization_id = o.id AND r.code = v.code);

INSERT INTO units (organization_id, name, code, unit_type)
SELECT o.id, v.name, v.code, v.unit_type
FROM (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o
CROSS JOIN (VALUES
  ('کیلوگرم', 'KG',     'WEIGHT'),
  ('تن',      'TON',    'WEIGHT'),
  ('عدد',     'PCS',    'QUANTITY'),
  ('بندیل',   'BUNDLE', 'QUANTITY')
) AS v(name, code, unit_type)
WHERE NOT EXISTS (SELECT 1 FROM units u WHERE u.organization_id = o.id AND u.code = v.code);

INSERT INTO product_categories (organization_id, name, code, description)
SELECT o.id, 'لوله و پروفیل', 'PIPE_PROFILE', 'Pipe and profile products'
FROM (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o
WHERE NOT EXISTS (SELECT 1 FROM product_categories pc WHERE pc.organization_id = o.id AND pc.code = 'PIPE_PROFILE');

INSERT INTO products (organization_id, category_id, name, code, description, default_unit_id)
SELECT o.id, pc.id, 'لوله گازی 2 اینچ', 'GAS-PIPE-2IN', 'Demo gas pipe product', u.id
FROM (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o
JOIN product_categories pc ON pc.organization_id = o.id AND pc.code = 'PIPE_PROFILE'
JOIN units u ON u.organization_id = o.id AND u.code = 'KG'
WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.organization_id = o.id AND p.code = 'GAS-PIPE-2IN');

INSERT INTO customers (organization_id, customer_type, name, national_id, mobile, phone, address, credit_limit)
SELECT o.id, 'COMPANY', 'مشتری آزمایشی TradeFlow', 'DEMO-CUSTOMER-ID',
       '09120000000', '02100000001', 'آدرس آزمایشی', 0
FROM (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o
WHERE NOT EXISTS (SELECT 1 FROM customers c WHERE c.organization_id = o.id AND c.name = 'مشتری آزمایشی TradeFlow');

-- specification template + fields for the demo category
INSERT INTO product_specification_templates (organization_id, category_id, name, code, description)
SELECT o.id, pc.id, 'مشخصات لوله و پروفیل', 'PIPE_PROFILE_SPEC', 'Demo specification template'
FROM (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o
JOIN product_categories pc ON pc.organization_id = o.id AND pc.code = 'PIPE_PROFILE'
WHERE NOT EXISTS (SELECT 1 FROM product_specification_templates t
                   WHERE t.organization_id = o.id AND t.code = 'PIPE_PROFILE_SPEC');

INSERT INTO product_specification_fields (organization_id, template_id, name, code, data_type, is_required, display_order, options)
SELECT t.organization_id, t.id, v.name, v.code, v.data_type, v.is_required, v.display_order, v.options::jsonb
FROM product_specification_templates t
JOIN (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o ON o.id = t.organization_id
CROSS JOIN (VALUES
  ('قطر',         'DIAMETER',     'SELECT',  TRUE,  1, '["1/2","1","2","3"]'),
  ('ضخامت (mm)',  'THICKNESS_MM', 'DECIMAL', FALSE, 2, NULL),
  ('گرید',        'GRADE',        'TEXT',    FALSE, 3, NULL)
) AS v(name, code, data_type, is_required, display_order, options)
WHERE t.code = 'PIPE_PROFILE_SPEC'
  AND NOT EXISTS (SELECT 1 FROM product_specification_fields f WHERE f.template_id = t.id AND f.code = v.code);

INSERT INTO product_specification_values (organization_id, product_id, field_id, value_option)
SELECT p.organization_id, p.id, f.id, '2'
FROM products p
JOIN (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o ON o.id = p.organization_id
JOIN product_specification_templates t ON t.organization_id = p.organization_id AND t.code = 'PIPE_PROFILE_SPEC'
JOIN product_specification_fields f ON f.template_id = t.id AND f.code = 'DIAMETER'
WHERE p.code = 'GAS-PIPE-2IN'
  AND NOT EXISTS (SELECT 1 FROM product_specification_values v WHERE v.product_id = p.id AND v.field_id = f.id);

-- users: one per role, argon2id (t=3, m=65536 KiB, p=4)
INSERT INTO users (organization_id, role_id, first_name, last_name, mobile, email, username, password_hash)
SELECT o.id, r.id, v.first_name, v.last_name, v.mobile, v.email, v.username, v.password_hash
FROM (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o
CROSS JOIN (VALUES
  ('ADMIN',      'TradeFlow', 'Admin',      '09120000001', 'admin@tradeflow.local',      'admin',      '$argon2id$v=19$m=65536,t=3,p=4$ta9y4Q/R1EvlNWWzMvjjlg$ndwWO7ci4Y4BzWMov+PGC/mfBoukuc3+PGlJMu5oZZI'),
  ('SALES',      'TradeFlow', 'Sales',      '09120000002', 'sales@tradeflow.local',      'sales',      '$argon2id$v=19$m=65536,t=3,p=4$1Ny5MSRR1SVt/HaZ6vrt/A$zCg7dBDPDo9yqz8TuxPn+OTt9jZdCZ4PQWCdGlMpiTU'),
  ('ACCOUNTING', 'TradeFlow', 'Accounting', '09120000003', 'accounting@tradeflow.local', 'accounting', '$argon2id$v=19$m=65536,t=3,p=4$AWXaBo5/uEn2I4+9NcHnjw$Yo0mPTStcLUH0r1qGWGMfng7RV5KG7dbp4g16kTeiDE')
) AS v(role_code, first_name, last_name, mobile, email, username, password_hash)
JOIN roles r ON r.organization_id = o.id AND r.code = v.role_code
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.organization_id = o.id AND u.username = v.username);

-- legacy databases seeded by the old 999: upgrade the placeholder hash, and only that exact placeholder
UPDATE users u SET password_hash = '$argon2id$v=19$m=65536,t=3,p=4$ta9y4Q/R1EvlNWWzMvjjlg$ndwWO7ci4Y4BzWMov+PGC/mfBoukuc3+PGlJMu5oZZI'
FROM (SELECT id FROM organizations WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID' AND code = 'DEMO') o
WHERE u.organization_id = o.id AND u.username = 'admin' AND u.password_hash = 'TEMPORARY_PASSWORD_HASH';
