-- TradeFlow
-- Migration: 001_initial_mvp
-- Purpose: Initial MVP database structure
-- Round 3: executable application of all accepted MF-001..MF-012 decisions

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE schema_migrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    checksum VARCHAR(128),
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_schema_migrations_version UNIQUE (version)
);

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    legal_name TEXT,
    national_id VARCHAR(50),
    economic_code VARCHAR(50),
    registration_number VARCHAR(50),
    phone VARCHAR(50),
    email VARCHAR(255),
    address TEXT,
    postal_code VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_roles_org_code UNIQUE (organization_id, code)
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    role_id UUID NOT NULL REFERENCES roles(id),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    mobile VARCHAR(30),
    email VARCHAR(255),
    username VARCHAR(100) NOT NULL,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_users_org_username UNIQUE (organization_id, username)
);

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    customer_type VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    national_id VARCHAR(50),
    economic_code VARCHAR(50),
    registration_number VARCHAR(50),
    mobile VARCHAR(30),
    phone VARCHAR(50),
    email VARCHAR(255),
    address TEXT,
    postal_code VARCHAR(20),
    credit_limit NUMERIC(20,0) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_customers_type CHECK (customer_type IN ('INDIVIDUAL', 'COMPANY')),
    CONSTRAINT chk_customers_credit_limit CHECK (credit_limit >= 0),
    CONSTRAINT uq_customers_org_name UNIQUE (organization_id, name)
);

CREATE UNIQUE INDEX uq_customers_org_national_id
    ON customers (organization_id, national_id)
    WHERE national_id IS NOT NULL;

CREATE UNIQUE INDEX uq_customers_org_economic_code
    ON customers (organization_id, economic_code)
    WHERE economic_code IS NOT NULL;

CREATE TABLE product_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    parent_id UUID REFERENCES product_categories(id),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_product_categories_org_code UNIQUE (organization_id, code)
);

CREATE TABLE units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) NOT NULL,
    unit_type VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_units_org_code UNIQUE (organization_id, code),
    CONSTRAINT chk_units_type CHECK (unit_type IN ('QUANTITY','WEIGHT','LENGTH','AREA','VOLUME','TIME'))
);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    category_id UUID NOT NULL REFERENCES product_categories(id),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(100) NOT NULL,
    description TEXT,
    default_unit_id UUID NOT NULL REFERENCES units(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_products_org_code UNIQUE (organization_id, code),
    CONSTRAINT uq_products_org_name UNIQUE (organization_id, name)
);

CREATE TABLE product_specification_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    category_id UUID REFERENCES product_categories(id),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_spec_templates_org_code UNIQUE (organization_id, code)
);

CREATE TABLE product_specification_fields (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    template_id UUID NOT NULL REFERENCES product_specification_templates(id),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(100) NOT NULL,
    data_type VARCHAR(30) NOT NULL,
    is_required BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    display_order INTEGER NOT NULL DEFAULT 0,
    options JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_spec_fields_template_code UNIQUE (template_id, code),
    CONSTRAINT chk_spec_fields_data_type CHECK (
        data_type IN ('TEXT','NUMBER','DECIMAL','BOOLEAN','DATE','SELECT','MULTI_SELECT')
    )
);

CREATE TABLE product_specification_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    product_id UUID NOT NULL REFERENCES products(id),
    field_id UUID NOT NULL REFERENCES product_specification_fields(id),
    value_text TEXT,
    value_number BIGINT,
    value_decimal NUMERIC(18,6),
    value_boolean BOOLEAN,
    value_date DATE,
    value_option TEXT,
    value_options JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_spec_values_product_field UNIQUE (product_id, field_id),
    CONSTRAINT chk_spec_values_at_most_one_value CHECK (
        ((value_text IS NOT NULL)::INTEGER +
         (value_number IS NOT NULL)::INTEGER +
         (value_decimal IS NOT NULL)::INTEGER +
         (value_boolean IS NOT NULL)::INTEGER +
         (value_date IS NOT NULL)::INTEGER +
         (value_option IS NOT NULL)::INTEGER +
         (value_options IS NOT NULL)::INTEGER) <= 1
    )
);

CREATE TABLE purchase_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    request_number VARCHAR(50) NOT NULL,
    customer_id UUID NOT NULL REFERENCES customers(id),
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    request_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requested_delivery_date TIMESTAMPTZ,
    subtotal NUMERIC(20,0) NOT NULL DEFAULT 0,
    discount_total NUMERIC(20,0) NOT NULL DEFAULT 0,
    tax_total NUMERIC(20,0) NOT NULL DEFAULT 0,
    grand_total NUMERIC(20,0) NOT NULL DEFAULT 0,
    notes TEXT,
    created_by UUID NOT NULL REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_purchase_requests_org_number UNIQUE (organization_id, request_number),
    CONSTRAINT chk_purchase_requests_status CHECK (status IN ('DRAFT','SUBMITTED','CANCELLED')),
    CONSTRAINT chk_purchase_requests_amounts CHECK (
        subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND grand_total >= 0
    ),
    CONSTRAINT chk_purchase_requests_grand_total_consistency CHECK (
        grand_total = subtotal - discount_total + tax_total
    ),
    CONSTRAINT chk_purchase_requests_delivery_date CHECK (
        requested_delivery_date IS NULL OR requested_delivery_date >= request_date
    )
);

CREATE TABLE purchase_request_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    purchase_request_id UUID NOT NULL REFERENCES purchase_requests(id),
    product_id UUID NOT NULL REFERENCES products(id),
    quantity NUMERIC(18,3) NOT NULL,
    unit_id UUID NOT NULL REFERENCES units(id),
    bundle_count NUMERIC(18,0) NOT NULL DEFAULT 0,
    -- Canonical unit for estimated_weight in MVP is KG.
    estimated_weight NUMERIC(18,3),
    unit_price NUMERIC(20,0) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(20,0) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(20,0) NOT NULL DEFAULT 0,
    line_total NUMERIC(20,0) NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_purchase_request_items_id_org UNIQUE (id, organization_id),
    CONSTRAINT chk_request_items_quantity CHECK (quantity > 0),
    CONSTRAINT chk_request_items_bundle_count CHECK (bundle_count >= 0),
    CONSTRAINT chk_request_items_weight CHECK (estimated_weight IS NULL OR estimated_weight >= 0),
    CONSTRAINT chk_request_items_amounts CHECK (
        unit_price >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND line_total >= 0
    ),
    CONSTRAINT chk_request_items_discount_not_exceed CHECK (
        discount_amount <= (quantity * unit_price)
    ),
    CONSTRAINT chk_request_items_line_total_consistency CHECK (
        line_total = ROUND(
            (quantity * unit_price) - discount_amount + tax_amount,
            0
        )
    )
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID REFERENCES users(id),
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID,
    action VARCHAR(50) NOT NULL,
    old_data JSONB,
    new_data JSONB,
    description TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_refresh_tokens_hash UNIQUE (token_hash)
);

-- Composite uniqueness required for tenant-safe foreign keys.
ALTER TABLE roles ADD CONSTRAINT uq_roles_id_organization UNIQUE (id, organization_id);
ALTER TABLE users ADD CONSTRAINT uq_users_id_organization UNIQUE (id, organization_id);
ALTER TABLE customers ADD CONSTRAINT uq_customers_id_organization UNIQUE (id, organization_id);
ALTER TABLE product_categories ADD CONSTRAINT uq_product_categories_id_organization UNIQUE (id, organization_id);
ALTER TABLE units ADD CONSTRAINT uq_units_id_organization UNIQUE (id, organization_id);
ALTER TABLE products ADD CONSTRAINT uq_products_id_organization UNIQUE (id, organization_id);
ALTER TABLE product_specification_templates ADD CONSTRAINT uq_spec_templates_id_organization UNIQUE (id, organization_id);
ALTER TABLE product_specification_fields ADD CONSTRAINT uq_spec_fields_id_organization UNIQUE (id, organization_id);
ALTER TABLE purchase_requests ADD CONSTRAINT uq_purchase_requests_id_organization UNIQUE (id, organization_id);

ALTER TABLE users
    ADD CONSTRAINT fk_users_role_same_organization
    FOREIGN KEY (role_id, organization_id) REFERENCES roles (id, organization_id);

ALTER TABLE product_categories
    ADD CONSTRAINT fk_product_categories_parent_same_organization
    FOREIGN KEY (parent_id, organization_id) REFERENCES product_categories (id, organization_id);

ALTER TABLE products
    ADD CONSTRAINT fk_products_category_same_organization
    FOREIGN KEY (category_id, organization_id) REFERENCES product_categories (id, organization_id);

ALTER TABLE products
    ADD CONSTRAINT fk_products_unit_same_organization
    FOREIGN KEY (default_unit_id, organization_id) REFERENCES units (id, organization_id);

ALTER TABLE product_specification_templates
    ADD CONSTRAINT fk_spec_templates_category_same_organization
    FOREIGN KEY (category_id, organization_id) REFERENCES product_categories (id, organization_id);

ALTER TABLE product_specification_fields
    ADD CONSTRAINT fk_spec_fields_template_same_organization
    FOREIGN KEY (template_id, organization_id) REFERENCES product_specification_templates (id, organization_id);

ALTER TABLE product_specification_values
    ADD CONSTRAINT uq_spec_values_id_organization UNIQUE (id, organization_id);

ALTER TABLE product_specification_values
    ADD CONSTRAINT fk_spec_values_product_same_organization
    FOREIGN KEY (product_id, organization_id) REFERENCES products (id, organization_id);

ALTER TABLE product_specification_values
    ADD CONSTRAINT fk_spec_values_field_same_organization
    FOREIGN KEY (field_id, organization_id) REFERENCES product_specification_fields (id, organization_id);

ALTER TABLE purchase_requests
    ADD CONSTRAINT fk_purchase_requests_customer_same_organization
    FOREIGN KEY (customer_id, organization_id) REFERENCES customers (id, organization_id);

ALTER TABLE purchase_requests
    ADD CONSTRAINT fk_purchase_requests_created_by_same_organization
    FOREIGN KEY (created_by, organization_id) REFERENCES users (id, organization_id);

ALTER TABLE purchase_requests
    ADD CONSTRAINT fk_purchase_requests_updated_by_same_organization
    FOREIGN KEY (updated_by, organization_id) REFERENCES users (id, organization_id);

ALTER TABLE purchase_request_items
    ADD CONSTRAINT fk_request_items_request_same_organization
    FOREIGN KEY (purchase_request_id, organization_id) REFERENCES purchase_requests (id, organization_id);

ALTER TABLE purchase_request_items
    ADD CONSTRAINT fk_request_items_product_same_organization
    FOREIGN KEY (product_id, organization_id) REFERENCES products (id, organization_id);

ALTER TABLE purchase_request_items
    ADD CONSTRAINT fk_request_items_unit_same_organization
    FOREIGN KEY (unit_id, organization_id) REFERENCES units (id, organization_id);

ALTER TABLE audit_logs
    ADD CONSTRAINT uq_audit_logs_id_organization UNIQUE (id, organization_id);

ALTER TABLE audit_logs
    ADD CONSTRAINT fk_audit_logs_user_same_organization
    FOREIGN KEY (user_id, organization_id) REFERENCES users (id, organization_id);

-- Indexes
CREATE INDEX idx_roles_organization ON roles (organization_id);
CREATE INDEX idx_users_organization ON users (organization_id);
CREATE INDEX idx_users_role ON users (organization_id, role_id);
CREATE INDEX idx_customers_organization ON customers (organization_id);
CREATE INDEX idx_customers_name ON customers (organization_id, name);
CREATE INDEX idx_products_organization ON products (organization_id);
CREATE INDEX idx_products_category ON products (organization_id, category_id);
CREATE INDEX idx_products_name ON products (organization_id, name);
CREATE INDEX idx_product_categories_organization ON product_categories (organization_id);
CREATE INDEX idx_product_categories_parent ON product_categories (organization_id, parent_id);
CREATE INDEX idx_units_organization ON units (organization_id);
CREATE INDEX idx_spec_templates_organization ON product_specification_templates (organization_id);
CREATE INDEX idx_spec_fields_template_order ON product_specification_fields (organization_id, template_id, display_order);
CREATE INDEX idx_spec_values_product ON product_specification_values (organization_id, product_id);
CREATE INDEX idx_spec_values_field ON product_specification_values (organization_id, field_id);
CREATE INDEX idx_purchase_requests_organization_date ON purchase_requests (organization_id, request_date);
CREATE INDEX idx_purchase_requests_status ON purchase_requests (organization_id, status);
CREATE INDEX idx_purchase_requests_customer ON purchase_requests (organization_id, customer_id);
CREATE INDEX idx_purchase_requests_created_by ON purchase_requests (organization_id, created_by);
CREATE INDEX idx_purchase_request_items_request ON purchase_request_items (organization_id, purchase_request_id);
CREATE INDEX idx_purchase_request_items_product ON purchase_request_items (organization_id, product_id);
CREATE INDEX idx_audit_logs_organization_date ON audit_logs (organization_id, created_at);
CREATE INDEX idx_audit_logs_user ON audit_logs (organization_id, user_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs (organization_id, entity_type, entity_id);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens (expires_at);

-- Automatic updated_at management
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_organizations_updated_at BEFORE UPDATE ON organizations FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_roles_updated_at BEFORE UPDATE ON roles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_customers_updated_at BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_product_categories_updated_at BEFORE UPDATE ON product_categories FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_units_updated_at BEFORE UPDATE ON units FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_products_updated_at BEFORE UPDATE ON products FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_product_specification_templates_updated_at BEFORE UPDATE ON product_specification_templates FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_product_specification_fields_updated_at BEFORE UPDATE ON product_specification_fields FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_product_specification_values_updated_at BEFORE UPDATE ON product_specification_values FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_purchase_requests_updated_at BEFORE UPDATE ON purchase_requests FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_purchase_request_items_updated_at BEFORE UPDATE ON purchase_request_items FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Parent totals are rebuilt from child rows. The parent row is locked first.
CREATE OR REPLACE FUNCTION recompute_purchase_request_totals(p_purchase_request_id UUID)
RETURNS VOID AS $$
DECLARE
    v_subtotal NUMERIC(20,0);
    v_discount_total NUMERIC(20,0);
    v_tax_total NUMERIC(20,0);
    v_grand_total NUMERIC(20,0);
BEGIN
    PERFORM 1
    FROM purchase_requests
    WHERE id = p_purchase_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT
        COALESCE(SUM(ROUND(quantity * unit_price, 0)), 0),
        COALESCE(SUM(discount_amount), 0),
        COALESCE(SUM(tax_amount), 0),
        COALESCE(SUM(line_total), 0)
    INTO v_subtotal, v_discount_total, v_tax_total, v_grand_total
    FROM purchase_request_items
    WHERE purchase_request_id = p_purchase_request_id;

    UPDATE purchase_requests
    SET subtotal = v_subtotal,
        discount_total = v_discount_total,
        tax_total = v_tax_total,
        grand_total = v_grand_total,
        updated_at = NOW()
    WHERE id = p_purchase_request_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_recompute_purchase_request_totals()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM recompute_purchase_request_totals(OLD.purchase_request_id);
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' AND OLD.purchase_request_id IS DISTINCT FROM NEW.purchase_request_id THEN
        PERFORM recompute_purchase_request_totals(OLD.purchase_request_id);
        PERFORM recompute_purchase_request_totals(NEW.purchase_request_id);
        RETURN NEW;
    ELSE
        PERFORM recompute_purchase_request_totals(NEW.purchase_request_id);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER recalc_purchase_request_totals
AFTER INSERT OR UPDATE OR DELETE ON purchase_request_items
FOR EACH ROW
EXECUTE FUNCTION trg_recompute_purchase_request_totals();

-- Schema migration registration
INSERT INTO schema_migrations (version, name)
VALUES ('001', 'initial_mvp')
ON CONFLICT (version) DO NOTHING;
