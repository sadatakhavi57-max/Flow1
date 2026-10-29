-- TradeFlow
-- Migration: 004_pre_invoices
-- Contract: SLICE_01_CONTRACT.md section 26 (Stage 4 - pre-invoice, ADR-060).  Scope - exactly these items, nothing else:
--   1. pre_invoices          immutable commercial snapshot of a SUBMITTED purchase request
--   2. pre_invoice_items     the snapshot of its items
--   3. pre_invoice_documents the server-generated PDF (bytes, SHA-256, status) - separate from the commercial status
--   4. guards: state machine, immutability, no deletion, "one active document" rules, PDF integrity
-- NOT touched: 001, 002, 003, runner.py, 998, 999.  The number counter is ORGANIZATION_REQUEST_COUNTERS from 002, used by the
-- Service with the series 'PI-<jalali year>' (ADR-057): NO new counter table and NO DDL on the counter.
-- Runs inside the runner's per-migration transaction.  Forward only: the runner has no down-migration (take a backup first).
--
-- Conventions copied from 001/002: composite same-organization foreign keys via UNIQUE (id, organization_id); money is
-- NUMERIC(20,0); quantity/estimated_weight NUMERIC(18,3); bundle_count NUMERIC(18,0); line_total = ROUND(q*p - d + t, 0);
-- state/immutability violations raise SQLSTATE 55000 (the API reports STATE_CONFLICT); internal-consistency violations
-- raise 23514 with a constraint name that the API does NOT map to a client error (they would be Service bugs).

-- ---------------------------------------------------------------------------
-- 1. pre_invoices
-- ---------------------------------------------------------------------------
CREATE TABLE pre_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    source_request_id UUID NOT NULL,
    -- document chain: the first document of a chain has chain_id = id; a replacement (supersedes_id) keeps the chain_id
    chain_id UUID NOT NULL,
    supersedes_id UUID,
    -- assigned ONLY at issue time (a DRAFT has neither number nor version)
    pre_invoice_number VARCHAR(60),
    version INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',

    -- snapshot: the purchase request at the moment the DRAFT was made (the request is frozen once SUBMITTED)
    request_number VARCHAR(50) NOT NULL,
    request_date TIMESTAMPTZ NOT NULL,
    requested_delivery_date TIMESTAMPTZ,
    request_notes TEXT,

    -- snapshot: seller (the organization)
    seller_name TEXT NOT NULL,
    seller_legal_name TEXT,
    seller_national_id VARCHAR(50),
    seller_economic_code VARCHAR(50),
    seller_registration_number VARCHAR(50),
    seller_phone VARCHAR(50),
    seller_email VARCHAR(255),
    seller_address TEXT,
    seller_postal_code VARCHAR(20),

    -- snapshot: customer (credit_limit is deliberately NOT copied)
    customer_id UUID NOT NULL,
    customer_type VARCHAR(20) NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_national_id VARCHAR(50),
    customer_economic_code VARCHAR(50),
    customer_registration_number VARCHAR(50),
    customer_mobile VARCHAR(30),
    customer_phone VARCHAR(50),
    customer_email VARCHAR(255),
    customer_address TEXT,
    customer_postal_code VARCHAR(20),

    -- snapshot: money, copied from the request header (same logic as 001; nothing is recomputed here)
    subtotal NUMERIC(20,0) NOT NULL,
    discount_total NUMERIC(20,0) NOT NULL,
    tax_total NUMERIC(20,0) NOT NULL,
    grand_total NUMERIC(20,0) NOT NULL,

    -- lifecycle
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    issued_by UUID,
    issued_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    cancelled_by UUID,
    cancelled_at TIMESTAMPTZ,
    cancel_reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_pre_invoices_id_organization UNIQUE (id, organization_id),
    CONSTRAINT uq_pre_invoices_chain_version UNIQUE (organization_id, chain_id, version),
    CONSTRAINT uq_pre_invoices_number_version UNIQUE (organization_id, pre_invoice_number, version),

    CONSTRAINT chk_pre_invoices_status CHECK (status IN ('DRAFT', 'ISSUED', 'SUPERSEDED', 'CANCELLED')),
    CONSTRAINT chk_pre_invoices_version CHECK (version IS NULL OR version >= 1),
    CONSTRAINT chk_pre_invoices_not_self_superseding CHECK (supersedes_id IS NULL OR supersedes_id <> id),
    CONSTRAINT chk_pre_invoices_chain_root CHECK (supersedes_id IS NOT NULL OR chain_id = id),
    -- number, version, issued_at and issued_by exist together: all after issue, none before it
    CONSTRAINT chk_pre_invoices_issue_consistency CHECK (
        (issued_at IS NULL) = (pre_invoice_number IS NULL)
        AND (issued_at IS NULL) = (version IS NULL)
        AND (issued_at IS NULL) = (issued_by IS NULL)
    ),
    CONSTRAINT chk_pre_invoices_status_shape CHECK (
        (status = 'DRAFT' AND issued_at IS NULL AND superseded_at IS NULL AND cancelled_at IS NULL)
        OR (status = 'ISSUED' AND issued_at IS NOT NULL AND superseded_at IS NULL AND cancelled_at IS NULL)
        OR (status = 'SUPERSEDED' AND issued_at IS NOT NULL AND superseded_at IS NOT NULL AND cancelled_at IS NULL)
        OR (status = 'CANCELLED' AND cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL AND superseded_at IS NULL
            AND (issued_at IS NULL OR cancel_reason IS NOT NULL))
    ),
    CONSTRAINT chk_pre_invoices_cancel_reason CHECK (
        cancel_reason IS NULL OR (char_length(cancel_reason) BETWEEN 1 AND 500 AND cancel_reason = btrim(cancel_reason))
    ),
    CONSTRAINT chk_pre_invoices_amounts CHECK (
        subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND grand_total >= 0
    ),
    CONSTRAINT chk_pre_invoices_grand_total_consistency CHECK (
        grand_total = subtotal - discount_total + tax_total
    ),

    CONSTRAINT fk_pre_invoices_source_request
        FOREIGN KEY (source_request_id, organization_id) REFERENCES purchase_requests (id, organization_id),
    CONSTRAINT fk_pre_invoices_customer
        FOREIGN KEY (customer_id, organization_id) REFERENCES customers (id, organization_id),
    CONSTRAINT fk_pre_invoices_created_by
        FOREIGN KEY (created_by, organization_id) REFERENCES users (id, organization_id),
    CONSTRAINT fk_pre_invoices_issued_by
        FOREIGN KEY (issued_by, organization_id) REFERENCES users (id, organization_id),
    CONSTRAINT fk_pre_invoices_cancelled_by
        FOREIGN KEY (cancelled_by, organization_id) REFERENCES users (id, organization_id),
    CONSTRAINT fk_pre_invoices_supersedes
        FOREIGN KEY (supersedes_id, organization_id) REFERENCES pre_invoices (id, organization_id),
    CONSTRAINT fk_pre_invoices_chain
        FOREIGN KEY (chain_id, organization_id) REFERENCES pre_invoices (id, organization_id)
);

-- "Active" = ISSUED.  These partial unique indexes are the last line of defence; the Service takes the request-header
-- lock first (contract 14.2) and answers 409 before reaching them.
CREATE UNIQUE INDEX uq_pre_invoices_issued_per_request
    ON pre_invoices (organization_id, source_request_id) WHERE status = 'ISSUED';
CREATE UNIQUE INDEX uq_pre_invoices_draft_per_request
    ON pre_invoices (organization_id, source_request_id) WHERE status = 'DRAFT';
CREATE UNIQUE INDEX uq_pre_invoices_issued_per_chain
    ON pre_invoices (organization_id, chain_id) WHERE status = 'ISSUED';
-- a document number is allocated once, with version 1; later versions of the chain reuse it
CREATE UNIQUE INDEX uq_pre_invoices_number_first_version
    ON pre_invoices (organization_id, pre_invoice_number) WHERE version = 1;
-- a document is replaced at most once (a cancelled DRAFT replacement does not occupy the slot)
CREATE UNIQUE INDEX uq_pre_invoices_one_successor
    ON pre_invoices (organization_id, supersedes_id) WHERE supersedes_id IS NOT NULL AND status <> 'CANCELLED';

CREATE INDEX idx_pre_invoices_source_request ON pre_invoices (organization_id, source_request_id);
CREATE INDEX idx_pre_invoices_status_created ON pre_invoices (organization_id, status, created_at);
CREATE INDEX idx_pre_invoices_customer ON pre_invoices (organization_id, customer_id);
CREATE INDEX idx_pre_invoices_number ON pre_invoices (organization_id, pre_invoice_number);
CREATE INDEX idx_pre_invoices_chain ON pre_invoices (organization_id, chain_id);
CREATE INDEX idx_pre_invoices_created_by ON pre_invoices (organization_id, created_by);

-- ---------------------------------------------------------------------------
-- 2. pre_invoice_items
-- ---------------------------------------------------------------------------
CREATE TABLE pre_invoice_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    pre_invoice_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    source_item_id UUID,
    product_id UUID NOT NULL,
    product_code VARCHAR(100) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    unit_id UUID NOT NULL,
    unit_code VARCHAR(20) NOT NULL,
    unit_name VARCHAR(100) NOT NULL,
    quantity NUMERIC(18,3) NOT NULL,
    bundle_count NUMERIC(18,0) NOT NULL,
    estimated_weight NUMERIC(18,3),
    unit_price NUMERIC(20,0) NOT NULL,
    discount_amount NUMERIC(20,0) NOT NULL,
    tax_amount NUMERIC(20,0) NOT NULL,
    line_total NUMERIC(20,0) NOT NULL,
    notes TEXT,
    specifications JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_pre_invoice_items_id_organization UNIQUE (id, organization_id),
    CONSTRAINT uq_pre_invoice_items_line_no UNIQUE (pre_invoice_id, line_no),
    CONSTRAINT chk_pre_invoice_items_line_no CHECK (line_no >= 1),
    CONSTRAINT chk_pre_invoice_items_quantity CHECK (quantity > 0),
    CONSTRAINT chk_pre_invoice_items_bundle_count CHECK (bundle_count >= 0),
    CONSTRAINT chk_pre_invoice_items_weight CHECK (estimated_weight IS NULL OR estimated_weight >= 0),
    CONSTRAINT chk_pre_invoice_items_amounts CHECK (
        unit_price >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND line_total >= 0
    ),
    CONSTRAINT chk_pre_invoice_items_discount_not_exceed CHECK (discount_amount <= (quantity * unit_price)),
    CONSTRAINT chk_pre_invoice_items_line_total_consistency CHECK (
        line_total = ROUND((quantity * unit_price) - discount_amount + tax_amount, 0)
    ),
    CONSTRAINT chk_pre_invoice_items_specifications_array CHECK (jsonb_typeof(specifications) = 'array'),

    CONSTRAINT fk_pre_invoice_items_pre_invoice
        FOREIGN KEY (pre_invoice_id, organization_id) REFERENCES pre_invoices (id, organization_id),
    CONSTRAINT fk_pre_invoice_items_source_item
        FOREIGN KEY (source_item_id, organization_id) REFERENCES purchase_request_items (id, organization_id),
    CONSTRAINT fk_pre_invoice_items_product
        FOREIGN KEY (product_id, organization_id) REFERENCES products (id, organization_id),
    CONSTRAINT fk_pre_invoice_items_unit
        FOREIGN KEY (unit_id, organization_id) REFERENCES units (id, organization_id)
);

CREATE INDEX idx_pre_invoice_items_pre_invoice ON pre_invoice_items (organization_id, pre_invoice_id, line_no);
CREATE INDEX idx_pre_invoice_items_product ON pre_invoice_items (organization_id, product_id);

-- ---------------------------------------------------------------------------
-- 3. pre_invoice_documents (the PDF).  One row per pre-invoice, created pending at issue.
--    Status is independent of the commercial status.  A 'ready' document is final.
--    attempt_count / window_* implement the retry policy (min 60 s between attempts, at most 1 initial + 3 retries per
--    15-minute window); the Service owns the policy, the database keeps the counters consistent.
-- ---------------------------------------------------------------------------
CREATE TABLE pre_invoice_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    pre_invoice_id UUID NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'pending',
    pdf_data BYTEA,
    pdf_sha256 VARCHAR(64),
    pdf_size INTEGER,
    template_version VARCHAR(30),
    generated_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    window_started_at TIMESTAMPTZ,
    window_attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    last_error_code VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_pre_invoice_documents_id_organization UNIQUE (id, organization_id),
    CONSTRAINT uq_pre_invoice_documents_pre_invoice UNIQUE (organization_id, pre_invoice_id),
    CONSTRAINT chk_pre_invoice_documents_status CHECK (status IN ('pending', 'ready', 'failed')),
    CONSTRAINT chk_pre_invoice_documents_shape CHECK (
        (status = 'ready' AND pdf_data IS NOT NULL AND pdf_sha256 IS NOT NULL AND pdf_size IS NOT NULL
            AND template_version IS NOT NULL AND generated_at IS NOT NULL AND last_error_code IS NULL)
        OR (status = 'pending' AND pdf_data IS NULL AND pdf_sha256 IS NULL AND pdf_size IS NULL AND generated_at IS NULL)
        OR (status = 'failed' AND pdf_data IS NULL AND pdf_sha256 IS NULL AND pdf_size IS NULL AND generated_at IS NULL
            AND last_error_code IS NOT NULL)
    ),
    -- 10 MiB cap; the stored size and SHA-256 must describe the stored bytes; the bytes must start with %PDF-
    CONSTRAINT chk_pre_invoice_documents_size CHECK (pdf_size IS NULL OR (pdf_size > 0 AND pdf_size <= 10485760)),
    CONSTRAINT chk_pre_invoice_documents_integrity CHECK (
        pdf_data IS NULL OR (
            pdf_size = octet_length(pdf_data)
            AND pdf_sha256 = encode(sha256(pdf_data), 'hex')
            AND substring(pdf_data FROM 1 FOR 5) = '\x255044462d'::bytea
        )
    ),
    CONSTRAINT chk_pre_invoice_documents_attempts CHECK (
        attempt_count >= 0 AND window_attempt_count >= 0 AND window_attempt_count <= attempt_count
    ),
    CONSTRAINT chk_pre_invoice_documents_error_code CHECK (
        last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]{0,49}$'
    ),
    CONSTRAINT fk_pre_invoice_documents_pre_invoice
        FOREIGN KEY (pre_invoice_id, organization_id) REFERENCES pre_invoices (id, organization_id)
);

-- ---------------------------------------------------------------------------
-- 4a. guard: pre_invoices
--     Lock mode is FOR UPDATE on the parent request, the same mode the request triggers of 002 use (contract 14.2).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_pre_invoices_guard()
RETURNS TRIGGER AS $$
DECLARE
    v_req_status VARCHAR(30);
    v_prev       pre_invoices%ROWTYPE;
    v_n          BIGINT;
    v_sub        NUMERIC;
    v_disc       NUMERIC;
    v_tax        NUMERIC;
    v_grand      NUMERIC;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'pre-invoice % cannot be deleted (cancel it instead)', OLD.id USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'a pre-invoice is created as DRAFT only' USING ERRCODE = '55000';
        END IF;
        SELECT status INTO v_req_status FROM purchase_requests
         WHERE id = NEW.source_request_id AND organization_id = NEW.organization_id FOR UPDATE;
        IF NOT FOUND OR v_req_status <> 'SUBMITTED' THEN
            RAISE EXCEPTION 'a pre-invoice can only be made from a SUBMITTED purchase request' USING ERRCODE = '55000';
        END IF;
        IF NEW.supersedes_id IS NOT NULL THEN
            SELECT * INTO v_prev FROM pre_invoices
             WHERE id = NEW.supersedes_id AND organization_id = NEW.organization_id FOR UPDATE;
            IF NOT FOUND OR v_prev.status <> 'ISSUED' THEN
                RAISE EXCEPTION 'only an ISSUED pre-invoice can be superseded' USING ERRCODE = '55000';
            END IF;
            IF v_prev.chain_id <> NEW.chain_id OR v_prev.source_request_id = NEW.source_request_id THEN
                RAISE EXCEPTION 'a replacement keeps the chain and comes from a different purchase request'
                    USING ERRCODE = '23514', CONSTRAINT = 'chk_pre_invoices_chain_consistency';
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    -- UPDATE ---------------------------------------------------------------
    IF NEW IS NOT DISTINCT FROM OLD THEN
        RETURN NEW;
    END IF;

    -- identity and the whole snapshot never change, in any state (a DRAFT is not editable either)
    IF (NEW.organization_id, NEW.source_request_id, NEW.chain_id, NEW.supersedes_id, NEW.created_by, NEW.created_at,
        NEW.request_number, NEW.request_date, NEW.requested_delivery_date, NEW.request_notes,
        NEW.seller_name, NEW.seller_legal_name, NEW.seller_national_id, NEW.seller_economic_code,
        NEW.seller_registration_number, NEW.seller_phone, NEW.seller_email, NEW.seller_address, NEW.seller_postal_code,
        NEW.customer_id, NEW.customer_type, NEW.customer_name, NEW.customer_national_id, NEW.customer_economic_code,
        NEW.customer_registration_number, NEW.customer_mobile, NEW.customer_phone, NEW.customer_email,
        NEW.customer_address, NEW.customer_postal_code,
        NEW.subtotal, NEW.discount_total, NEW.tax_total, NEW.grand_total)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.source_request_id, OLD.chain_id, OLD.supersedes_id, OLD.created_by, OLD.created_at,
        OLD.request_number, OLD.request_date, OLD.requested_delivery_date, OLD.request_notes,
        OLD.seller_name, OLD.seller_legal_name, OLD.seller_national_id, OLD.seller_economic_code,
        OLD.seller_registration_number, OLD.seller_phone, OLD.seller_email, OLD.seller_address, OLD.seller_postal_code,
        OLD.customer_id, OLD.customer_type, OLD.customer_name, OLD.customer_national_id, OLD.customer_economic_code,
        OLD.customer_registration_number, OLD.customer_mobile, OLD.customer_phone, OLD.customer_email,
        OLD.customer_address, OLD.customer_postal_code,
        OLD.subtotal, OLD.discount_total, OLD.tax_total, OLD.grand_total) THEN
        RAISE EXCEPTION 'pre-invoice % identity and snapshot are immutable', OLD.id USING ERRCODE = '55000';
    END IF;

    IF NEW.status = OLD.status THEN
        -- same status: the lifecycle columns are frozen too (only updated_at may move)
        IF (NEW.pre_invoice_number, NEW.version, NEW.issued_by, NEW.issued_at, NEW.superseded_at,
            NEW.cancelled_by, NEW.cancelled_at, NEW.cancel_reason)
           IS DISTINCT FROM
           (OLD.pre_invoice_number, OLD.version, OLD.issued_by, OLD.issued_at, OLD.superseded_at,
            OLD.cancelled_by, OLD.cancelled_at, OLD.cancel_reason) THEN
            RAISE EXCEPTION 'pre-invoice % is % and its lifecycle data is frozen', OLD.id, OLD.status
                USING ERRCODE = '55000';
        END IF;
        NEW.updated_at := NOW();
        RETURN NEW;
    END IF;

    IF NOT (
           (OLD.status = 'DRAFT'  AND NEW.status IN ('ISSUED', 'CANCELLED'))
        OR (OLD.status = 'ISSUED' AND NEW.status IN ('SUPERSEDED', 'CANCELLED'))
    ) THEN
        RAISE EXCEPTION 'illegal pre-invoice status transition % -> %', OLD.status, NEW.status USING ERRCODE = '55000';
    END IF;

    IF NEW.status = 'ISSUED' THEN
        -- DRAFT -> ISSUED: the request is still SUBMITTED, the items add up to the header, the number/version fit the chain
        SELECT status INTO v_req_status FROM purchase_requests
         WHERE id = NEW.source_request_id AND organization_id = NEW.organization_id FOR UPDATE;
        IF NOT FOUND OR v_req_status <> 'SUBMITTED' THEN
            RAISE EXCEPTION 'the source purchase request is no longer SUBMITTED' USING ERRCODE = '55000';
        END IF;

        SELECT count(*), COALESCE(SUM(ROUND(quantity * unit_price, 0)), 0), COALESCE(SUM(discount_amount), 0),
               COALESCE(SUM(tax_amount), 0), COALESCE(SUM(line_total), 0)
          INTO v_n, v_sub, v_disc, v_tax, v_grand
          FROM pre_invoice_items WHERE pre_invoice_id = NEW.id;
        IF v_n = 0 OR (v_sub, v_disc, v_tax, v_grand)
                      IS DISTINCT FROM (NEW.subtotal, NEW.discount_total, NEW.tax_total, NEW.grand_total) THEN
            RAISE EXCEPTION 'pre-invoice % items do not match its totals', NEW.id
                USING ERRCODE = '23514', CONSTRAINT = 'chk_pre_invoices_items_consistency';
        END IF;

        IF NEW.supersedes_id IS NULL THEN
            IF NEW.version <> 1 THEN
                RAISE EXCEPTION 'the first document of a chain has version 1'
                    USING ERRCODE = '23514', CONSTRAINT = 'chk_pre_invoices_version_chain';
            END IF;
        ELSE
            SELECT * INTO v_prev FROM pre_invoices
             WHERE id = NEW.supersedes_id AND organization_id = NEW.organization_id;
            IF NOT FOUND OR v_prev.status <> 'SUPERSEDED' THEN
                RAISE EXCEPTION 'the superseded pre-invoice must be marked SUPERSEDED first' USING ERRCODE = '55000';
            END IF;
            IF NEW.version <> v_prev.version + 1 OR NEW.pre_invoice_number <> v_prev.pre_invoice_number THEN
                RAISE EXCEPTION 'a replacement has the next version and keeps the document number'
                    USING ERRCODE = '23514', CONSTRAINT = 'chk_pre_invoices_version_chain';
            END IF;
        END IF;
    ELSIF NEW.status = 'SUPERSEDED' THEN
        -- ISSUED -> SUPERSEDED happens only as part of issuing the replacement (which is still a DRAFT at that moment)
        IF NOT EXISTS (SELECT 1 FROM pre_invoices s
                        WHERE s.supersedes_id = OLD.id AND s.organization_id = OLD.organization_id AND s.status = 'DRAFT') THEN
            RAISE EXCEPTION 'a pre-invoice is superseded only by issuing its replacement' USING ERRCODE = '55000';
        END IF;
    END IF;

    -- number/version/issued_* may be set only by DRAFT -> ISSUED; the cancel columns only by -> CANCELLED
    IF OLD.status <> 'DRAFT' AND (NEW.pre_invoice_number, NEW.version, NEW.issued_by, NEW.issued_at)
                                 IS DISTINCT FROM (OLD.pre_invoice_number, OLD.version, OLD.issued_by, OLD.issued_at) THEN
        RAISE EXCEPTION 'pre-invoice % number, version and issue data are immutable once issued', OLD.id
            USING ERRCODE = '55000';
    END IF;

    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pre_invoices_guard
BEFORE INSERT OR UPDATE OR DELETE ON pre_invoices
FOR EACH ROW EXECUTE FUNCTION trg_pre_invoices_guard();

-- ---------------------------------------------------------------------------
-- 4b. guard: pre_invoice_items - written once, while the parent is a DRAFT, never changed or deleted.
--     The parent is locked FOR UPDATE (same mode as the guard above and as the service).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_pre_invoice_items_guard()
RETURNS TRIGGER AS $$
DECLARE
    v_status VARCHAR(20);
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'pre-invoice items are immutable (% rejected)', TG_OP USING ERRCODE = '55000';
    END IF;
    SELECT status INTO v_status FROM pre_invoices
     WHERE id = NEW.pre_invoice_id AND organization_id = NEW.organization_id FOR UPDATE;
    IF FOUND AND v_status <> 'DRAFT' THEN
        RAISE EXCEPTION 'pre-invoice is % : items are frozen', v_status USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pre_invoice_items_guard
BEFORE INSERT OR UPDATE OR DELETE ON pre_invoice_items
FOR EACH ROW EXECUTE FUNCTION trg_pre_invoice_items_guard();

-- ---------------------------------------------------------------------------
-- 4c. guard: pre_invoice_documents
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_pre_invoice_documents_guard()
RETURNS TRIGGER AS $$
DECLARE
    v_issued_at TIMESTAMPTZ;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'pre-invoice documents are never deleted' USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        SELECT issued_at INTO v_issued_at FROM pre_invoices
         WHERE id = NEW.pre_invoice_id AND organization_id = NEW.organization_id;
        IF NOT FOUND OR v_issued_at IS NULL THEN
            RAISE EXCEPTION 'a document exists only for an issued pre-invoice' USING ERRCODE = '55000';
        END IF;
        IF NEW.status <> 'pending' OR NEW.attempt_count <> 0 THEN
            RAISE EXCEPTION 'a document starts pending with no attempts' USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    -- UPDATE
    IF NEW IS NOT DISTINCT FROM OLD THEN
        RETURN NEW;
    END IF;
    IF OLD.status = 'ready' THEN
        RAISE EXCEPTION 'a ready document and its hash are final' USING ERRCODE = '55000';
    END IF;
    IF (NEW.organization_id, NEW.pre_invoice_id, NEW.created_at) IS DISTINCT FROM
       (OLD.organization_id, OLD.pre_invoice_id, OLD.created_at) THEN
        RAISE EXCEPTION 'document identity is immutable' USING ERRCODE = '55000';
    END IF;
    IF NEW.attempt_count < OLD.attempt_count THEN
        RAISE EXCEPTION 'attempt_count never decreases' USING ERRCODE = '55000';
    END IF;
    IF OLD.status = 'failed' AND NEW.status = 'pending' THEN
        RAISE EXCEPTION 'illegal document status transition failed -> pending' USING ERRCODE = '55000';
    END IF;
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pre_invoice_documents_guard
BEFORE INSERT OR UPDATE OR DELETE ON pre_invoice_documents
FOR EACH ROW EXECUTE FUNCTION trg_pre_invoice_documents_guard();
