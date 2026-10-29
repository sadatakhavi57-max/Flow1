-- TradeFlow
-- Migration: 003_org_code_and_username
-- Contract: SLICE_01_CONTRACT.md section 3.1 (D16, D17).  Scope - exactly these four items, nothing else:
--   1. add, backfill and finalize organizations.code
--   2. format / normalization / uniqueness constraints on the code
--   3. a trigger that makes the code immutable
--   4. CHECK that makes users.username trimmed + lower-case
-- 001, 002, runner.py and 999 are NOT touched.  Runs inside the runner's per-migration transaction.
-- Any violation (duplicate demo org, unnormalized username, ...) fails loudly; nothing is "fixed" silently.

-- 1a. column, nullable for the backfill
ALTER TABLE organizations ADD COLUMN code VARCHAR(50);

-- 1b. backfill (all before the immutability trigger exists)
--  (a) the dev-seed organization: BOTH natural keys written by the old 999 must match
DO $$
DECLARE n INTEGER;
BEGIN
    SELECT count(*) INTO n FROM organizations
     WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID';
    IF n > 1 THEN
        RAISE EXCEPTION '003: % organizations match the demo natural key (name + national_id); resolve manually', n
            USING ERRCODE = '23505';
    END IF;
END $$;

UPDATE organizations SET code = 'DEMO'
 WHERE name = 'TradeFlow Demo' AND national_id = 'DEMO-NATIONAL-ID';

--  (b) every other organization: ORG-000001, ORG-000002, ... in (created_at, id) order
WITH ranked AS (
    SELECT id, row_number() OVER (ORDER BY created_at, id) AS n
      FROM organizations
     WHERE code IS NULL
)
UPDATE organizations o
   SET code = 'ORG-' || lpad(r.n::text, 6, '0')
  FROM ranked r
 WHERE o.id = r.id;

-- 1c. finalize
ALTER TABLE organizations ALTER COLUMN code SET NOT NULL;

-- 2. constraints
ALTER TABLE organizations
    ADD CONSTRAINT chk_organizations_code_normalized CHECK (code = upper(btrim(code))),
    ADD CONSTRAINT chk_organizations_code_format     CHECK (code ~ '^[A-Z0-9][A-Z0-9_-]{1,49}$'),
    ADD CONSTRAINT uq_organizations_code             UNIQUE (code);

-- 3. immutability - created only AFTER the backfill
CREATE OR REPLACE FUNCTION trg_organizations_code_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.code IS DISTINCT FROM OLD.code THEN
        RAISE EXCEPTION 'organizations.code is immutable (organization %)', OLD.id
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_organizations_code_immutable
BEFORE UPDATE OF code ON organizations
FOR EACH ROW EXECUTE FUNCTION trg_organizations_code_immutable();

-- 4. usernames are stored trimmed and lower-case (fails if an existing row violates it)
ALTER TABLE users
    ADD CONSTRAINT chk_users_username_normalized CHECK (username = lower(btrim(username)));
