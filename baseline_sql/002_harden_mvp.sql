-- TradeFlow
-- Migration: 002_harden_mvp
-- Purpose: Fix defects proven by behavioural tests against PostgreSQL 16 (tests/regression.sql).
--
-- OUT OF SCOPE on purpose (need an ADR first): money model/scale, multi-organisation login, Pre-Invoice.
-- This file does NOT change any money column type. The rounding contract is: ROUND_HALF_UP on
-- (quantity * unit_price - discount_amount + tax_amount); see tests/money_contract.py.
--
-- Contracts implemented here
--   C1  requested_delivery_date is a calendar DATE (business day, Asia/Tehran), may equal the request day.
--   C2  customer name is NOT unique. Only national_id / economic_code identify a customer.
--   C3  national_id / economic_code are stored normalised: ASCII digits, no whitespace/ZWNJ, '' -> NULL.
--   C4  audit_logs is append-only (no UPDATE / DELETE / TRUNCATE).
--   C5  purchase_requests state machine: DRAFT -> SUBMITTED | CANCELLED, SUBMITTED -> CANCELLED. Nothing else.
--       Items and commercial header fields are frozen once the request leaves DRAFT. Only DRAFT is deletable.
--   C6  Each item carries its own immutable-by-design specification SNAPSHOT (code/name/type/value),
--       independent of later changes to product specification master data.
--   C7  request numbers come from a per-organisation, per-series counter (concurrency-safe, no MAX()+1).

-- ---------------------------------------------------------------------------
-- Guard: Persian text handling (normalisation below, search, sorting) is only correct on UTF8.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF current_setting('server_encoding') <> 'UTF8' THEN
        RAISE EXCEPTION 'TradeFlow requires a UTF8 database (this one is %). Create it with ENCODING ''UTF8''.',
            current_setting('server_encoding');
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- C1  delivery date
-- ---------------------------------------------------------------------------
ALTER TABLE purchase_requests DROP CONSTRAINT chk_purchase_requests_delivery_date;

ALTER TABLE purchase_requests
    ALTER COLUMN requested_delivery_date TYPE DATE
    USING (requested_delivery_date AT TIME ZONE 'Asia/Tehran')::date;

ALTER TABLE purchase_requests
    ADD CONSTRAINT chk_purchase_requests_delivery_date CHECK (
        requested_delivery_date IS NULL
        OR requested_delivery_date >= (request_date AT TIME ZONE 'Asia/Tehran')::date
    );

-- ---------------------------------------------------------------------------
-- C2  customer name is not an identity
-- ---------------------------------------------------------------------------
ALTER TABLE customers DROP CONSTRAINT uq_customers_org_name;
-- idx_customers_name (non-unique, organization_id + name) from 001 remains for search.

-- ---------------------------------------------------------------------------
-- C3  identifier normalisation
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION normalize_identifier(p TEXT)
RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(
        regexp_replace(
            translate(p, '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'),
            '[[:space:]‌‎‏ ]', '', 'g'),
        '')
$$;

CREATE OR REPLACE FUNCTION trg_customers_normalize_identifiers()
RETURNS TRIGGER AS $$
BEGIN
    NEW.national_id   := normalize_identifier(NEW.national_id);
    NEW.economic_code := normalize_identifier(NEW.economic_code);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_customers_normalize_identifiers
BEFORE INSERT OR UPDATE ON customers
FOR EACH ROW EXECUTE FUNCTION trg_customers_normalize_identifiers();

-- Normalise existing rows. If two existing customers collapse to the same identifier this
-- statement fails on the partial unique indexes, which is the correct (loud) outcome.
UPDATE customers SET national_id = national_id, economic_code = economic_code;

-- Back-stop for writers that bypass triggers (e.g. session_replication_role = replica).
ALTER TABLE customers
    ADD CONSTRAINT chk_customers_identifiers_normalized CHECK (
        national_id   IS NOT DISTINCT FROM normalize_identifier(national_id)
        AND economic_code IS NOT DISTINCT FROM normalize_identifier(economic_code)
    );

-- ---------------------------------------------------------------------------
-- C4  audit_logs append-only
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_audit_logs_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: % is not allowed', TG_OP
        USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_logs_no_update_delete
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION trg_audit_logs_append_only();

CREATE TRIGGER trg_audit_logs_no_truncate
BEFORE TRUNCATE ON audit_logs
FOR EACH STATEMENT EXECUTE FUNCTION trg_audit_logs_append_only();

-- ---------------------------------------------------------------------------
-- C5  state machine + freeze
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_purchase_requests_guard()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'purchase request % is % and cannot be deleted (cancel it instead)',
                OLD.request_number, OLD.status USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;

    -- Never changeable, in any state.
    IF (NEW.organization_id, NEW.request_number, NEW.created_by, NEW.created_at)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.request_number, OLD.created_by, OLD.created_at) THEN
        RAISE EXCEPTION 'organization_id, request_number, created_by and created_at are immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
           (OLD.status = 'DRAFT'     AND NEW.status IN ('SUBMITTED', 'CANCELLED'))
        OR (OLD.status = 'SUBMITTED' AND NEW.status = 'CANCELLED')
    ) THEN
        RAISE EXCEPTION 'illegal status transition % -> %', OLD.status, NEW.status
            USING ERRCODE = '55000';
    END IF;

    -- Outside DRAFT the commercial content is frozen (status, notes, updated_* may still change).
    IF OLD.status <> 'DRAFT' THEN
        IF (NEW.customer_id, NEW.request_date, NEW.requested_delivery_date,
            NEW.subtotal, NEW.discount_total, NEW.tax_total, NEW.grand_total)
           IS DISTINCT FROM
           (OLD.customer_id, OLD.request_date, OLD.requested_delivery_date,
            OLD.subtotal, OLD.discount_total, OLD.tax_total, OLD.grand_total) THEN
            RAISE EXCEPTION 'purchase request % is % and its commercial fields are frozen',
                OLD.request_number, OLD.status USING ERRCODE = '55000';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_purchase_requests_guard
BEFORE UPDATE OR DELETE ON purchase_requests
FOR EACH ROW EXECUTE FUNCTION trg_purchase_requests_guard();

-- The parent row is locked FOR UPDATE here, the same mode recompute_purchase_request_totals()
-- uses later in the statement. Same mode => concurrent writers queue instead of deadlocking,
-- and a concurrent submit cannot slip between the status check and the item write.
CREATE OR REPLACE FUNCTION trg_purchase_request_items_guard()
RETURNS TRIGGER AS $$
DECLARE
    v_request_id UUID;
    v_status     VARCHAR(30);
BEGIN
    IF TG_OP = 'UPDATE' AND
       (NEW.purchase_request_id, NEW.organization_id) IS DISTINCT FROM
       (OLD.purchase_request_id, OLD.organization_id) THEN
        RAISE EXCEPTION 'an item cannot be moved to another request or organization'
            USING ERRCODE = '55000';
    END IF;

    v_request_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.purchase_request_id
                         ELSE NEW.purchase_request_id END;

    SELECT status INTO v_status
    FROM purchase_requests
    WHERE id = v_request_id
    FOR UPDATE;

    IF FOUND AND v_status <> 'DRAFT' THEN
        RAISE EXCEPTION 'purchase request is % : items are frozen (% rejected)', v_status, TG_OP
            USING ERRCODE = '55000';
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_purchase_request_items_guard
BEFORE INSERT OR UPDATE OR DELETE ON purchase_request_items
FOR EACH ROW EXECUTE FUNCTION trg_purchase_request_items_guard();

-- ---------------------------------------------------------------------------
-- C6  item specification snapshot
--     Element shape: {"field_id": uuid, "field_code": str, "field_name": str,
--                     "data_type": str, "value": any}
--     The service writes the snapshot when the item is saved; later edits to templates/fields/
--     product values never touch it. Value-vs-data_type validation stays in the service layer.
-- ---------------------------------------------------------------------------
ALTER TABLE purchase_request_items
    ADD COLUMN specifications JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE purchase_request_items
    ADD CONSTRAINT chk_request_items_specifications_array
    CHECK (jsonb_typeof(specifications) = 'array');

CREATE OR REPLACE FUNCTION trg_request_items_validate_specifications()
RETURNS TRIGGER AS $$
DECLARE
    e        JSONB;
    v_id     UUID;
    v_total  INTEGER;
    v_unique INTEGER;
BEGIN
    -- Not an array: let chk_request_items_specifications_array reject it with its own message.
    IF jsonb_typeof(NEW.specifications) <> 'array' OR jsonb_array_length(NEW.specifications) = 0 THEN
        RETURN NEW;
    END IF;

    FOR e IN SELECT value FROM jsonb_array_elements(NEW.specifications) LOOP
        IF jsonb_typeof(e) <> 'object'
           OR NOT (e ?& ARRAY['field_id', 'field_code', 'field_name', 'data_type', 'value']) THEN
            RAISE EXCEPTION 'specification snapshot element must be an object with keys field_id, field_code, field_name, data_type, value'
                USING ERRCODE = '23514';
        END IF;

        BEGIN
            v_id := (e ->> 'field_id')::uuid;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'specification snapshot field_id is not a UUID: %', e ->> 'field_id'
                USING ERRCODE = '23514';
        END;

        PERFORM 1
        FROM product_specification_fields f
        WHERE f.id = v_id
          AND f.organization_id = NEW.organization_id
          AND f.code = e ->> 'field_code'
          AND f.data_type = e ->> 'data_type';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'specification snapshot references an unknown field, a field of another organization, or a code/data_type that does not match it: %', e ->> 'field_id'
                USING ERRCODE = '23503';
        END IF;
    END LOOP;

    SELECT count(*), count(DISTINCT x ->> 'field_id')
      INTO v_total, v_unique
      FROM jsonb_array_elements(NEW.specifications) AS x;
    IF v_total <> v_unique THEN
        RAISE EXCEPTION 'specification snapshot contains the same field more than once'
            USING ERRCODE = '23505';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_request_items_validate_specifications
BEFORE INSERT OR UPDATE OF specifications ON purchase_request_items
FOR EACH ROW EXECUTE FUNCTION trg_request_items_validate_specifications();

-- ---------------------------------------------------------------------------
-- C7  request number counters
--     series is chosen by the service (e.g. the Jalali year '1405'); the textual format of
--     the final number (prefix, padding) is deliberately NOT decided here.
--     The row lock taken by the upsert is held until the surrounding transaction ends, so
--     numbers are unique, ordered per series, and a rolled-back request gives its number back.
-- ---------------------------------------------------------------------------
CREATE TABLE organization_request_counters (
    organization_id UUID        NOT NULL REFERENCES organizations(id),
    series          VARCHAR(50) NOT NULL,
    last_number     BIGINT      NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_organization_request_counters PRIMARY KEY (organization_id, series),
    CONSTRAINT chk_request_counters_last_number CHECK (last_number >= 0)
);

CREATE OR REPLACE FUNCTION next_request_number(p_organization_id UUID, p_series TEXT)
RETURNS BIGINT
LANGUAGE sql AS $$
    INSERT INTO organization_request_counters AS c (organization_id, series, last_number)
    VALUES (p_organization_id, p_series, 1)
    ON CONFLICT (organization_id, series)
    DO UPDATE SET last_number = c.last_number + 1, updated_at = NOW()
    RETURNING last_number
$$;

-- ---------------------------------------------------------------------------
INSERT INTO schema_migrations (version, name)
VALUES ('002', 'harden_mvp')
ON CONFLICT (version) DO NOTHING;
