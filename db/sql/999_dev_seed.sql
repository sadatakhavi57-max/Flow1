-- Development seed only. Do not run in production.

-- TradeFlow development/demo seed data.
-- This file intentionally contains only non-production sample records.

INSERT INTO organizations (
    name, legal_name, national_id, economic_code, registration_number,
    phone, email, address, postal_code
)
SELECT
    'TradeFlow Demo', 'TradeFlow Demo Company', 'DEMO-NATIONAL-ID',
    'DEMO-ECONOMIC-CODE', 'DEMO-REG', '02100000000',
    'demo@tradeflow.local', 'Demo Address', '0000000000'
WHERE NOT EXISTS (
    SELECT 1 FROM organizations WHERE name = 'TradeFlow Demo'
);

INSERT INTO roles (organization_id, code, name, description)
SELECT o.id, 'ADMIN', 'Administrator', 'Full access to organization data and settings'
FROM organizations o
WHERE o.name = 'TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM roles r WHERE r.organization_id=o.id AND r.code='ADMIN');

INSERT INTO roles (organization_id, code, name, description)
SELECT o.id, 'SALES', 'Sales', 'Sales and customer management'
FROM organizations o
WHERE o.name = 'TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM roles r WHERE r.organization_id=o.id AND r.code='SALES');

INSERT INTO roles (organization_id, code, name, description)
SELECT o.id, 'ACCOUNTING', 'Accounting', 'Financial and accounting operations'
FROM organizations o
WHERE o.name = 'TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM roles r WHERE r.organization_id=o.id AND r.code='ACCOUNTING');

INSERT INTO units (organization_id, name, code, unit_type)
SELECT o.id, 'کیلوگرم', 'KG', 'WEIGHT' FROM organizations o
WHERE o.name='TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM units u WHERE u.organization_id=o.id AND u.code='KG');

INSERT INTO units (organization_id, name, code, unit_type)
SELECT o.id, 'تن', 'TON', 'WEIGHT' FROM organizations o
WHERE o.name='TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM units u WHERE u.organization_id=o.id AND u.code='TON');

INSERT INTO units (organization_id, name, code, unit_type)
SELECT o.id, 'عدد', 'PCS', 'QUANTITY' FROM organizations o
WHERE o.name='TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM units u WHERE u.organization_id=o.id AND u.code='PCS');

INSERT INTO units (organization_id, name, code, unit_type)
SELECT o.id, 'بندیل', 'BUNDLE', 'QUANTITY' FROM organizations o
WHERE o.name='TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM units u WHERE u.organization_id=o.id AND u.code='BUNDLE');

INSERT INTO product_categories (organization_id, name, code, description)
SELECT o.id, 'لوله و پروفیل', 'PIPE_PROFILE', 'Pipe and profile products'
FROM organizations o
WHERE o.name='TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM product_categories pc WHERE pc.organization_id=o.id AND pc.code='PIPE_PROFILE');

INSERT INTO products (organization_id, category_id, name, code, description, default_unit_id)
SELECT o.id, pc.id, 'لوله گازی 2 اینچ', 'GAS-PIPE-2IN',
       'Demo gas pipe product', u.id
FROM organizations o
JOIN product_categories pc ON pc.organization_id=o.id AND pc.code='PIPE_PROFILE'
JOIN units u ON u.organization_id=o.id AND u.code='KG'
WHERE o.name='TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM products p WHERE p.organization_id=o.id AND p.code='GAS-PIPE-2IN');

INSERT INTO customers (organization_id, customer_type, name, national_id, mobile, phone, address, credit_limit)
SELECT o.id, 'COMPANY', 'مشتری آزمایشی TradeFlow', 'DEMO-CUSTOMER-ID',
       '09120000000', '02100000001', 'آدرس آزمایشی', 0
FROM organizations o
WHERE o.name='TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM customers c WHERE c.organization_id=o.id AND c.name='مشتری آزمایشی TradeFlow');

-- Development-only placeholder. Production credentials must be created by Backend.
INSERT INTO users (organization_id, role_id, first_name, last_name, mobile, email, username, password_hash)
SELECT o.id, r.id, 'TradeFlow', 'Admin', '09120000001',
       'admin@tradeflow.local', 'admin', 'TEMPORARY_PASSWORD_HASH'
FROM organizations o
JOIN roles r ON r.organization_id=o.id AND r.code='ADMIN'
WHERE o.name='TradeFlow Demo'
  AND NOT EXISTS (SELECT 1 FROM users u WHERE u.organization_id=o.id AND u.username='admin');
