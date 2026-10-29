# TradeFlow — Slice 01 Contract

**Status:** **v7 — decisions D1–D17 and ADR-063 Accepted 2026-10-10** (approval record § 24); review rounds 1–4 applied (§§ 21–23, § 25). Round-4 proposals C and G were not adopted (D10, D4 unchanged, § 25); everything is binding. After approval, FastAPI is an implementation of this document; it is not a place to make architecture decisions.
**Baseline:** Baseline Hardened (`001` + `002` + `runner.py`), ADR-056 … ADR-063.
**Pipeline:** FastAPI → Service → Repository/DB → PostgreSQL. The Flet client never touches the database.
**Precedence on conflict:** migrations (what the database enforces) → this contract → `API_SPECIFICATION.md` / `WORKFLOW.md` / `UI_UX_SPECIFICATION.md`. If implementation reveals the contract is wrong, the contract is changed first (and, if scope changes, an ADR), then the code.

> **Decisions in this document that are mine, not yours.** Everything marked **[D#]** is a proposal I made to close a gap; it is listed again in § 20 for explicit approval. Everything not marked follows from the baseline, the ADRs or your last message.

## 0.1 Baseline verification (facts checked against the real SQL)

The review of v2 could only see SQL from an older Library copy and the docs ZIP did not contain the migrations. They are now shipped in `baseline_sql/` with `SHA256SUMS`, and the points raised against them were re-checked line by line:

| Claim in the review | Real `001_initial_mvp.sql` (sha256 `83e97dc8…05a5`) |
|---|---|
| `data_type` CHECK lacks `MULTI_SELECT` | line 161: `IN ('TEXT','NUMBER','DECIMAL','BOOLEAN','DATE','SELECT','MULTI_SELECT')` — present |
| `organization_id` missing on specification tables | `product_specification_fields` and `product_specification_values` both have `organization_id UUID NOT NULL REFERENCES organizations(id)`; `value_options JSONB` exists |
| only product `code` is unique | line 130: `CONSTRAINT uq_products_org_name UNIQUE (organization_id, name)` and `uq_products_org_code` — **both** exist |
| `bundle_count` is `NUMERIC(18,3)` | line 228: `bundle_count NUMERIC(18,0)` (18 integer digits, the contract regex is correct); `quantity` and `estimated_weight` are `NUMERIC(18,3)` |

`002_harden_mvp.sql` sha256 `ab93a670…ff9e`. The frozen `tradeflow_hardened.zip` itself contains `002`, `runner.py`, `999_dev_seed.sql` and `tests/`, **not** `001` (001 is the file you supplied); `baseline_sql/` therefore carries 001 too. `docs/DATA_MODEL.md` was machine-checked column-by-column and type-by-type against these two files (16 tables, 0 differences).

## 0. Corrections to the last proposal (found by reading the baseline)

The `specifications` sample in the last message cannot be accepted by the database as written:

| In the sample | What the database enforces | Contract |
|---|---|---|
| `"field_id": 12` | `field_id` must be a **UUID** of an existing `product_specification_fields` row of the same organization | UUID |
| `"data_type": "decimal"` | must be **exactly equal** to `product_specification_fields.data_type`, which is stored upper-case: `TEXT, NUMBER, DECIMAL, BOOLEAN, DATE, SELECT, MULTI_SELECT` | upper-case, copied from the field |
| `"field_code": "thickness"` | must be exactly equal to the field's stored `code` | copied from the field, never typed by the client |

The names, array structure, key set and snapshot semantics you proposed are kept unchanged.

---

## 1. Endpoints (Slice 01)

Base path `/api/v1`. All endpoints except login/refresh require `Authorization: Bearer <access_token>`.

```text
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout
GET    /auth/me

GET    /organizations
GET    /organizations/{id}

GET    /customers
POST   /customers
GET    /customers/{id}
PATCH  /customers/{id}

GET    /products
POST   /products
GET    /products/{id}
PATCH  /products/{id}
GET    /products/{id}/specifications
GET    /product-categories                      ← read-only lookup, ADR-063
GET    /units                                   ← read-only lookup, ADR-063

GET    /purchase-requests
POST   /purchase-requests
GET    /purchase-requests/{id}
PATCH  /purchase-requests/{id}
POST   /purchase-requests/{id}/submit
POST   /purchase-requests/{id}/cancel          ← added by ADR-062

POST   /purchase-requests/{id}/items
PATCH  /purchase-request-items/{id}
DELETE /purchase-request-items/{id}

POST   /purchase-requests/{id}/pricing
GET    /purchase-requests/{id}/pricing

GET    /audit-logs
```

Total: **29 endpoints** = the 27 listed in `MVP_SCOPE.md` § 3 (which includes `cancel`, ADR-062) + 2 read-only lookups (ADR-063). Nothing else is implemented, even if `API_SPECIFICATION.md` lists it.

## 2. Conventions

**Envelope.** `request_id` is present in **every** response (success and error); examples in this document omit it for brevity. Single resource / command: `{"data": {...}, "request_id": "<uuid>"}`. List: `{"items": [...], "page": 1, "page_size": 50, "total": 123}`. Error: `{"error": {"code", "message", "details", "request_id"}}` (§ 15). `204` has no body (logout only).

**Identifiers.** UUID strings. A malformed UUID in a path → `422 VALIDATION_ERROR`.

**Timestamps.** ISO 8601 UTC with microseconds (`2026-10-08T09:20:11.123456Z`). `requested_delivery_date` is `YYYY-MM-DD` (Asia/Tehran business day). **Calendar rule:** every date the API accepts or returns is **Gregorian**, `YYYY-MM-DD`, ASCII digits. Persian/Arabic-Indic digits in a date input are converted to ASCII before validation; the API never returns Jalali dates. Jalali display and input conversion are **client-only**. (The Jalali year inside `request_number` is an identifier series, not a date field.)

**Digits.** The API accepts Persian/Arabic-Indic digits in numeric strings and dates and normalizes them to ASCII before validation (same rule the database applies to customer identifiers). It always returns ASCII.

**Strings.** Trimmed; empty string → `null` for optional fields; unknown JSON keys → `422` (`extra = forbid`). `organization_id`, `id`, `created_*`, `updated_*`, `status` (except via submit/cancel), `request_number`, totals and `line_total` are never accepted from the body.

**Pagination.** `page` ≥ 1 (default 1), `page_size` 1–200 (default 50). Sorting is always deterministic: `created_at DESC, id DESC` unless stated.

**Organization context.** Every request is scoped by the `org` claim of the access token. No endpoint reads `organization_id` from body, query or path. Every repository method takes `organization_id` as a mandatory argument. A resource of another organization is indistinguishable from a missing one: `404`.

## 3. Authentication (ADR-059)

**Login** `POST /auth/login`

```json
{ "organization_code": "ORG-001", "username": "admin", "password": "…" }
```

`organization_code` is normalized (trim, digits to ASCII, **upper-case**) and resolved through `organizations.code` (migration 003, § 3.1). Response `200`:

```json
{ "data": {
  "access_token": "…", "refresh_token": "…", "token_type": "bearer", "expires_in": 3600,
  "user": { "id": "uuid", "username": "admin", "first_name": "…", "last_name": "…",
            "role": { "code": "ADMIN", "name": "Administrator" },
            "organization": { "id": "uuid", "code": "ORG-001", "name": "…" } } } }
```

Failure for **any** reason (unknown organization, unknown user, wrong password, inactive organization/user/role) → one identical `401 AUTH_INVALID_CREDENTIALS`, with comparable response time (a dummy hash check runs when the user is unknown).

**Tokens [D10].**
- Access token: signed JWT (HS256, secret from environment), 3600 s, claims `sub` (user id), `org` (organization id), `iat`, `exp`, `jti`. The role is **not** trusted from the token: on every request the service loads user, role and organization from the database and rejects inactive ones (`401 AUTH_TOKEN_INVALID`).
- Refresh token: opaque, 256-bit random, delivered once; only its SHA-256 hash is stored in `refresh_tokens.token_hash`; lifetime 30 days; **rotated** on every refresh (old row gets `revoked_at`). Presenting an already-revoked or expired token → `401 AUTH_REFRESH_INVALID` (and every active refresh token of that user is revoked, since reuse signals theft).
- Logout `POST /auth/logout` body `{"refresh_token": "…"}` → revokes it, `204 No Content` with an **empty body**. Because a 204 has no envelope, the request id is returned in the **`X-Request-Id` response header**; every response (success and error, any status) carries that header, and the JSON envelope's `request_id` equals it.
- Password hashing: argon2id through `argon2-cffi`, with the **version pinned in the dependency lock file** and the parameters **set explicitly in configuration** (initial values: `time_cost=3`, `memory_cost=65536` KiB, `parallelism=4`, `hash_len=32`, `salt_len=16` — the library's current defaults, frozen here so an upgrade cannot change policy silently). A stored hash with older parameters is verified and re-hashed on the next successful login (`check_needs_rehash`). The dev placeholder `TEMPORARY_PASSWORD_HASH` never verifies.
- **Concurrent / duplicate refresh — chosen policy: duplicate-tolerant with a grace window [D10].** The Service runs `SELECT … FROM refresh_tokens WHERE token_hash = :h FOR UPDATE` inside the transaction that revokes the old row and inserts the new one, so two simultaneous refreshes with the same token serialize. For the presented token:
  1. *not revoked, not expired* → rotate: set `revoked_at = now()`, issue the new pair (`200`);
  2. *revoked ≤ 10 seconds ago* (`REFRESH_GRACE_SECONDS`, configuration, default 10) → **benign duplicate**: `401 AUTH_REFRESH_INVALID` with `details.reason = "ALREADY_ROTATED"`, **nothing else is revoked**, no token is returned (raw tokens are never stored, so the first result cannot be replayed). The winner's new token stays valid;
  3. *revoked more than 10 seconds ago*, expired, or unknown → real reuse: `401 AUTH_REFRESH_INVALID` with `details.reason = "INVALID"` and **all** active refresh tokens of that user are revoked (theft response).
  Consequences: one old token can never produce two valid new tokens; the single successful call always returns a token that is still valid after the race ends; the theft signal is delayed by at most 10 s. **Client rule:** refresh is single-flight — one in-flight refresh per session; on `ALREADY_ROTATED` the client waits for / reuses the result of its own in-flight call and never retries with the old token. No new column is needed (`revoked_at` is enough).
- **Logout** revokes only a refresh token whose `user_id` equals the caller (`sub`) and whose user belongs to the caller's organization; any other token → `401 AUTH_REFRESH_INVALID` (no hint that it exists). Logout invalidates the refresh token only: the **access JWT stays valid until its `exp` (≤ 1 h)**; there is no `jti` deny-list in Slice 01. That window is accepted [D10]; per-request database checks still reject a deactivated user/role/organization immediately.
- Usernames are matched after trim + lower-case (§ 3.1).

**Brute-force control [D10].** *Note: the limit is per key. It bounds attempts per `(organization_code, username, IP)`, not the total number of failed attempts or log events — many IPs or many usernames each get their own allowance; no global cap exists in Slice 01.* Failed logins are counted per (`organization_code`, `username`, client IP): after 10 failures in 15 minutes → `429 RATE_LIMITED` (+ `Retry-After`). In Slice 01 the counter is in-process memory, so the deployment **must run exactly one worker process**: the setting `WORKERS=1` is part of the deployment checklist and the application logs a startup warning if configured otherwise (with several workers the 10-in-15-minutes limit is not guaranteed). A shared store is out of scope (§ 19).

**`GET /auth/me`** → same `user` object as login.

## 3.1 Migration 003 specification (implemented after the v6 approval; `sql/003_org_code_and_username.sql`)

**Scope of 003 — exactly this list, nothing else** (001/002/runner/999 stay frozen):
1. add, backfill and finalize `organizations.code`;
2. format and uniqueness constraints on the code;
3. a trigger that makes the code immutable;
4. the CHECK that makes `users.username` normalized.

**`organizations.code` [D16]**
1. Stored **upper-case, already normalized**; format `^[A-Z0-9][A-Z0-9_-]{1,49}$`; `VARCHAR(50)`.
2. Case-insensitive uniqueness is achieved by *storing upper-case only* plus `CHECK (code = upper(btrim(code)))` and the format CHECK; a plain `UNIQUE (code)` then makes `ORG-001` and `org-001` the same value. Login upper-cases its input before the lookup.
3. **Backfill, in this order (all before the immutability trigger exists):**
   a. **The dev-seed organization, explicit exception:** the row with `name = 'TradeFlow Demo'` **and** `national_id = 'DEMO-NATIONAL-ID'` (both values written by the old `999_dev_seed.sql`) gets `code = 'DEMO'`. The double match keeps a real organization that merely shares the name from being renamed.
   b. **All other organizations**, in `created_at, id` order: `'ORG-' || lpad(n, 6, '0')` with `n = 1, 2, …` counted over those rows only (so the first non-demo organization is `ORG-000001`).
   c. Deterministic and collision-free by construction (the column is new; `DEMO` does not match the `ORG-` format of the others). If a duplicate is ever found the migration fails loudly; it never "fixes" it silently.
4. Sequence inside 003: add column nullable → backfill (a, b) → `SET NOT NULL` → add CHECKs → add `UNIQUE` → **only then** create the immutability trigger.
5. **Immutable after creation:** a `BEFORE UPDATE` trigger rejects a change of `code` (`55000`). Organization creation/management is outside Slice 01; codes are set by seed/admin SQL at creation.
6. Dev org code: `DEMO`.

**`users.username` [D17]:** stored trimmed and lower-case: `CHECK (username = lower(btrim(username)))` (existing seed value `admin` complies; if any existing row violates it the migration fails loudly). Login lower-cases and trims its input. This removes the `Admin` / `admin` ambiguity that `uq_users_org_username` (case-sensitive) would otherwise allow.

**Audit vocabulary CHECK (D4): not added in 003.** The closed sets live in Python enums with tests; a database CHECK on an append-only table would need a migration for every Phase-2 action (APPROVE, REJECT, …), and a wrong CHECK cannot be repaired by editing rows.

**Tests for 003** (run against a database that already holds data, including one seeded by the **old** 999): the old demo organization becomes `DEMO` and the others `ORG-000001…` in deterministic order; a real organization named `TradeFlow Demo` with another `national_id` is **not** given `DEMO`; backfill produces unique deterministic codes; `ORG-001` vs `org-001` collide; duplicate code rejected; code update rejected; username with upper-case or spaces rejected; runner applies 003 after 001/002 and refuses it before them; 003 is idempotent only through the runner's version check.

## 4. Authorization (coarse, role-based) [D5]

Slice 01 does **not** have permissions or RBAC. It has three fixed role codes (the codes in the dev seed) checked by the Service:

| Capability | ADMIN | SALES | ACCOUNTING |
|---|:-:|:-:|:-:|
| `me`, organizations (read) | ✔ | ✔ | ✔ |
| customers: read | ✔ | ✔ | ✔ |
| customers: create / patch | ✔ | ✔ | – |
| products + specifications: read | ✔ | ✔ | ✔ |
| products: create / patch | ✔ | – | – |
| purchase requests, pricing: read | ✔ | ✔ | ✔ |
| purchase requests: create | ✔ | ✔ | – |
| request / items / pricing: write, submit, cancel | any request | **own requests only** (`created_by` = caller) | – |
| audit-logs: read | ✔ | – | – |
| pre-invoices: read (list, get, PDF download) | ✔ | **own requests only** (source request `created_by` = caller) | ✔ |
| pre-invoices: create a DRAFT | ✔ | **own requests only** | – |
| pre-invoices: issue | ✔ | – | ✔ |
| pre-invoices: cancel a DRAFT | ✔ | **own requests only** | – |
| pre-invoices: cancel an ISSUED document | ✔ | – | ✔ |
| pre-invoices: generate / retry the PDF | ✔ | – | ✔ |

Denied → `403 FORBIDDEN_ROLE` (role lacks the capability) or `403 FORBIDDEN_NOT_OWNER` (SALES on someone else's request). The matrix lives in one place in code and is covered by a table-driven test. A real Permission model is a later ADR.

## 5. Organization

`GET /organizations` → `{"items": [<the caller's single organization>], …}`. `GET /organizations/{id}` → the organization if `id` equals the token's `org`, else `404`. Fields: `id, code, name, legal_name, national_id, economic_code, registration_number, phone, email, address, postal_code, is_active, created_at, updated_at`. The Settings screen is **read-only** in Slice 01 (no PATCH endpoint exists).

## 6. Customer contract

Resource: `id, customer_type, name, national_id, economic_code, registration_number, mobile, phone, email, address, postal_code, credit_limit, is_active, created_at, updated_at`.

- `POST`: required `customer_type` (`INDIVIDUAL`|`COMPANY`) and `name` (1–255). Optional others. `credit_limit`: integer string ≥ 0, default `"0"` (stored only; no credit control in MVP). `is_active` defaults `true`.
- `PATCH`: any subset of the above except `id`, plus the mandatory `updated_at` (§ 14.5) [D7]. Deactivation is `is_active=false`; there is no delete.
- `national_id` / `economic_code`: returned **as normalized by the database** (ASCII digits, no whitespace/ZWNJ/NBSP, empty → `null`).
- `name` is **not unique**.
- Duplicate `national_id` or `economic_code` in the organization → `409 DUPLICATE_IDENTIFIER`, `details: {"field": "national_id"|"economic_code"}`.
- List filters: `search` (case-insensitive contains on name, national_id, economic_code, mobile; digits normalized), `is_active`, `customer_type`. Default sort `name ASC, id ASC`.
- Audit: `CREATE` / `UPDATE` on `CUSTOMER`.

## 7. Product contract

Resource: `id, code, name, description, category {id, code, name}, default_unit {id, code, name, unit_type}, is_active, created_at, updated_at`.

- `POST` (ADMIN): required `code` (1–100), `name` (1–255), `category_id`, `default_unit_id`; optional `description`. Category and unit must exist, be active and belong to the organization.
- `PATCH`: any subset of `code, name, description, category_id, default_unit_id, is_active`, plus the mandatory `updated_at` (§ 14.5) [D7]. Changing `category_id` changes which specification fields are *applicable* in future items; existing item snapshots are untouched.
- Duplicate `code` **or** `name` in the organization → `409 DUPLICATE_RESOURCE`, `details.field` (both are unique in 001: `uq_products_org_code`, `uq_products_org_name`).
- List filters: `search`, `category_id`, `is_active`. Default sort `name ASC, id ASC`.
- Audit: `CREATE` / `UPDATE` on `PRODUCT`.

**`GET /products/{id}/specifications`** → applicable fields and the product's stored values:

```json
{ "data": { "product_id": "uuid", "fields": [
  { "field_id": "uuid", "code": "THICKNESS", "name": "ضخامت", "data_type": "DECIMAL",
    "is_required": true, "display_order": 1, "options": null, "value": "2.5" } ] } }
```

*Applicable* = active fields of active templates whose `category_id` equals the product's `category_id` [D3]. `value` is the product's stored value converted from the matching `value_*` column (or `null`). Order: `display_order ASC, code ASC`.

**Lookups (ADR-063) [D2/D15].** `GET /product-categories` and `GET /units` are **read-only**, organization-scoped lists for the product and item forms.
- `GET /product-categories`: `id, code, name, parent_id, is_active`; filters `is_active`, `search`; sort `name ASC, id ASC`.
- `GET /units`: `id, code, name, unit_type, is_active`; filters `is_active`, `unit_type`; sort `code ASC, id ASC`.
- Default filter is `is_active=true`, so forms never offer inactive choices; pass `is_active=false` to see inactive rows.
- All three roles may read them.

**Master data is not editable through the API in Slice 01.** Creating/editing categories, units, specification templates/fields and product specification values has no endpoints; it is done by seed/admin SQL. The UUIDs clients need come from the two lookup endpoints, never from documentation.

## 8. Purchase request contract

Resource (header): `id, request_number, status, customer {id, name}, request_date, requested_delivery_date, subtotal, discount_total, tax_total, grand_total, notes, created_by, updated_by, created_at, updated_at`. Detail adds `items: [Item]`. List rows add `item_count` instead of items. Money fields are integer strings.

**Create** `POST /purchase-requests` (ADMIN, SALES)

```json
{ "customer_id": "uuid", "requested_delivery_date": "2026-11-15", "notes": "…",
  "items": [ { …Item input… } ] }
```

`items` is optional. Money/quantity fields follow § 10. Everything happens in **one transaction**: customer check (exists, same organization, active) → `next_request_number` → insert header (`status = DRAFT`) → insert items → audit → commit. Any failure rolls back everything, including the counter. `201` + detail.

`requested_delivery_date` — optional (`null` allowed). Two **independent** rules, both required: (1) **Service:** a valid Gregorian date, not before **today in Asia/Tehran** (the same day is allowed) → else `422 VALIDATION_ERROR`; (2) **Database (defence in depth, migration 002 C1):** not before the request's own `request_date` (Tehran date), enforced by `chk_purchase_requests_delivery_date` → mapped `23514` → `422`. Neither replaces the other: on a later PATCH, rule (1) still compares with *today*, rule (2) with the creation date.

**Request number [D1 — your proposal, adopted].** `request_number = "<series>-<n:06d>"`, e.g. `1405-000001`, where `series` is the **Jalali year of the creation instant in Asia/Tehran** and `n` comes from `next_request_number(organization_id, series)`. The sequence restarts at 1 each Jalali year. If `n` exceeds 999 999 the number simply gets longer. The format is built in the Service; PostgreSQL stores the string only. `MAX()+1` is forbidden. The client never sends it.

**Update header** `PATCH /purchase-requests/{id}` (own/ADMIN): body may contain `customer_id`, `requested_delivery_date`, `notes`, and must contain `updated_at` (§ 17). **DRAFT only** — any other status → `409 STATE_CONFLICT`. **Content freeze at API level [D9]:** in `SUBMITTED` **and** `CANCELLED` nothing in the request can be edited through the API — header fields, **notes**, items, prices. The database is more permissive (it still lets `status`, `notes` and `updated_*` change); the API deliberately is not. Only `submit` and `cancel` change a non-draft request.

**Submit** `POST …/submit` (no body). Inside one transaction, after locking the header `FOR UPDATE`:
1. status must be `DRAFT` → else `409 STATE_CONFLICT`;
2. customer, every product and every unit still active → else `422 INACTIVE_REFERENCE`;
3. at least one item → else `422 SUBMIT_PRECONDITION_FAILED` (`reason: NO_ITEMS`);
4. every item has `unit_price > 0` [D6] (`reason: ITEM_PRICE_MISSING`, `item_id`);
5. every item carries all applicable fields with `is_required = true` [D6] (`reason: REQUIRED_SPECIFICATION_MISSING`, `item_id`, `field_id`).

Then `DRAFT → SUBMITTED`, `updated_by` set, audit `SUBMIT`. Repeating submit → `409 STATE_CONFLICT` (not a silent success).

**Cancel** `POST …/cancel` — ADR-062. Body `{"reason": "…"}` (required, 1–500 chars **after trimming**) [D8]. Allowed from `DRAFT` and `SUBMITTED`; from `CANCELLED` → `409`. Audit `CANCEL` with the reason in `description`. A cancelled request keeps all its data and is never deleted.

**State machine and freeze.** Exactly the database rules of ADR-061 (C5): `DRAFT→SUBMITTED`, `DRAFT→CANCELLED`, `SUBMITTED→CANCELLED`, nothing else. Outside `DRAFT`: header content, totals and **all items** are frozen (add, change, delete). Slice 01 exposes no way to delete a request, not even a draft [D12].

**List** `GET /purchase-requests`: filters `status`, `customer_id`, `created_from`, `created_to` (dates, Tehran), `search` (request number prefix/contains, customer name); sort `created_at DESC, id DESC`.

## 9. Item contract

Resource: `id, purchase_request_id, product {id, code, name}, unit {id, code, name}, quantity, bundle_count, estimated_weight, unit_price, discount_amount, tax_amount, line_total, notes, specifications, created_at, updated_at`.

**Create** `POST /purchase-requests/{id}/items` — input:

```json
{ "product_id": "uuid", "unit_id": "uuid", "quantity": "10.000",
  "bundle_count": "2", "estimated_weight": "1250.500",
  "unit_price": "125000", "discount_amount": "0", "tax_amount": "0",
  "notes": "…",
  "specifications": [ { "field_id": "uuid", "value": "2.5" } ] }
```

- Required: `product_id`, `quantity`. `unit_id` defaults to the product's `default_unit_id` [D2]. Prices default to `"0"`, `bundle_count` to `"0"`, `estimated_weight` to `null`, `specifications` to `[]`.
- Product and unit must exist in the organization and be **active** (`422 INACTIVE_REFERENCE`).
- The parent must be `DRAFT` (else `409 STATE_CONFLICT`).
- `line_total` is **computed by the Service** (§ 10) and written together with the item; the database re-checks it and rebuilds the header totals.
- Response `201`: `{"data": {"item": Item, "request": header}}` so the client has the new totals.

**Update** `PATCH /purchase-request-items/{id}`: any subset of the input fields; `product_id` may not change [D13] (delete and re-add instead). `specifications`, when present, **replaces the whole snapshot array**. Requires the item's `updated_at` (§ 17). Parent must be `DRAFT`. Response as create (`200`).

**Delete** `DELETE /purchase-request-items/{id}`: parent must be `DRAFT`. `200` with `{"data": {"request": header}}`. Audit `DELETE`.

Audit for items: `CREATE`/`UPDATE`/`DELETE` on `PURCHASE_REQUEST_ITEM`; for a price change `old_data`/`new_data` contain the changed price fields.

## 10. Money and Rial contract (ADR-058)

- Unit: **Rial**. All money is a whole number. JSON carries it only as a **string** of ASCII digits: `^(0|[1-9][0-9]{0,19})$`. A JSON number, a fractional string (`"125000.00"`, `"1.5"`), a negative value or a non-numeric value → `422 INVALID_MONEY`.
- Quantity: string `^[0-9]{1,15}(\.[0-9]{1,3})?$`, must be `> 0`. Estimated weight (KG): same shape, `≥ 0`, optional. `bundle_count`: integer string `^(0|[1-9][0-9]{0,17})$` (column is `NUMERIC(18,0)`: 18 digits is the real limit; 19 digits → `422 VALIDATION_ERROR` — **not** `INVALID_MONEY`: `bundle_count` is a count, not money).
- Calculation (Service, Python `decimal`): context precision 80, rounding `ROUND_HALF_UP`.
  `line_total = quantize( quantity × unit_price − discount_amount + tax_amount , 0, ROUND_HALF_UP )`
  The implementation must be the function validated by `tests/money_contract.py`; Python's default `ROUND_HALF_EVEN` is forbidden.
- Service pre-checks before the database does: `discount_amount ≤ quantity × unit_price`; `line_total ≥ 0`; `line_total` and each header total fit 20 digits → else `422 AMOUNT_OUT_OF_RANGE` (a PostgreSQL `22003` is mapped to the same code).
- Header totals are read back from the database after the write (the trigger rebuilds them); the Service never computes or accepts header totals itself.
- Display in Toman is a client concern; the API only speaks Rial. Responses of pricing endpoints include `"currency_unit": "RIAL"`.

## 11. Pricing endpoints

**`POST /purchase-requests/{id}/pricing`** (DRAFT only; same locking and checks as item update). Body sets prices of one or more items atomically (all or nothing):

```json
{ "updated_at": "…", "lines": [ { "item_id": "uuid", "unit_price": "125000",
                                  "discount_amount": "0", "tax_amount": "0" } ] }
```

Each line behaves like an item `PATCH` restricted to the three price fields. Response `200`: the pricing view below. Audit: one `UPDATE` on each changed `PURCHASE_REQUEST_ITEM` with old/new price fields [D14].

**`GET /purchase-requests/{id}/pricing`**:

```json
{ "data": { "request_id": "uuid", "status": "DRAFT", "currency_unit": "RIAL",
  "lines": [ { "item_id": "uuid", "product": {…}, "quantity": "10.000",
               "unit_price": "125000", "discount_amount": "0", "tax_amount": "0",
               "line_total": "1250000" } ],
  "subtotal": "1250000", "discount_total": "0", "tax_total": "0", "grand_total": "1250000",
  "updated_at": "…" } }
```

Price history is not a separate structure in Slice 01: material price changes are visible as `UPDATE` rows in `GET /audit-logs` (ADMIN).

## 12. `specifications` contract

**Client input** (per item): `"specifications": [ { "field_id": "<uuid>", "value": <json> } ]` — exactly these two keys. `field_code`, `field_name`, `data_type` sent by a client → `422` (the server is the only author of the snapshot).

**Stored and returned snapshot** (this is what the database trigger checks):

```json
[ { "field_id": "uuid", "field_code": "THICKNESS", "field_name": "ضخامت",
    "data_type": "DECIMAL", "value": "2.5" } ]
```

The Service builds each element from the current `product_specification_fields` row at save time. Later changes to templates, fields or product values never alter the snapshot.

**Per element, in this order** (first failure wins, `422 SPECIFICATION_INVALID`, `details: [{field_id, reason}]`):

| Reason | Condition |
|---|---|
| `UNKNOWN_FIELD` | no such field in the organization |
| `NOT_APPLICABLE` | field is not applicable to the item's product (§ 7) |
| `INACTIVE_FIELD` | field `is_active = false` |
| `DUPLICATE_FIELD` | same `field_id` twice in the array |
| `INVALID_VALUE` | value fails the type rule below |

Missing required fields are **not** an error while the request is a draft; they are checked at submit (§ 8). A value of `null` is invalid (omit the element instead).

**Value rules (canonical JSON form of `value`).** Input digits are normalized to ASCII first.

| `data_type` | Accepted | Canonical stored value |
|---|---|---|
| `TEXT` | string, 1–1000 chars after trim | trimmed string |
| `NUMBER` (integer) | string `^-?[0-9]{1,18}$` | no leading zeros, `-0` → `"0"` |
| `DECIMAL` | string `^-?[0-9]{1,12}(\.[0-9]{1,6})?$` (Arabic `٫` accepted as `.`) | no leading zeros, trailing fractional zeros removed (`"2.50"` → `"2.5"`, `"3.0"` → `"3"`) |
| `BOOLEAN` | JSON `true` / `false` only (the strings `"true"`, `"1"` are rejected) | same |
| `DATE` | string `YYYY-MM-DD`, a real Gregorian date | same |
| `SELECT` | string equal to one of the field's `options` | same |
| `MULTI_SELECT` | non-empty array of distinct strings, each in `options` | array in the order of the field's `options` |

`options` format in Slice 01: a JSON array of strings [D3]. JSON numbers are rejected for `NUMBER`/`DECIMAL` (no float round-trips).

These are the cases the first-endpoint tests must cover (§ 18): DECIMAL `"ABC"` ✗, `"125.50"` ✓ (→ `"125.5"`), `"1,5"` ✗; NUMBER `"10"` ✓, `"10.5"` ✗, `"۱۰"` ✓ (→ `"10"`); BOOLEAN `true` ✓, `"true"` ✗; DATE `"2026-02-30"` ✗, `"2026-10-08"` ✓; SELECT in/out of options; MULTI_SELECT with duplicate / unknown option ✗; TEXT empty ✗.

## 13. Audit contract

`audit_logs` is append-only (database-enforced). Rows are written by the Service **in the same transaction** as the change they describe — a change without its audit row cannot commit, and a rolled-back change leaves no audit row.

**Actions (closed set)** [D4]: `CREATE`, `UPDATE`, `DELETE`, `SUBMIT`, `CANCEL`, `LOGIN`, `LOGOUT`, `ISSUE`, `SUPERSEDE`, `PDF_GENERATE`, `PDF_FAIL`. The last four are Stage 4 (§ 26). `LOGOUT` is added to your list because `/auth/logout` is in the endpoint set. **Entity types (closed set):** `USER`, `CUSTOMER`, `PRODUCT`, `PURCHASE_REQUEST`, `PURCHASE_REQUEST_ITEM`, `PRE_INVOICE` (Stage 4). Both are Python enums used by every writer; unit tests fail on any other string. The database has no CHECK for them (see [D4] for the option of adding one in migration 003).

| Event | action | entity_type | old_data / new_data |
|---|---|---|---|
| successful login | LOGIN | USER | – / `{}` ; `ip_address` set |
| logout | LOGOUT | USER | – |
| customer / product create | CREATE | CUSTOMER / PRODUCT | – / full row |
| customer / product patch | UPDATE | same | changed fields before / after |
| request create | CREATE | PURCHASE_REQUEST | – / header (+`item_count`) |
| request header patch | UPDATE | PURCHASE_REQUEST | changed fields before / after |
| submit | SUBMIT | PURCHASE_REQUEST | `{status: DRAFT}` / `{status: SUBMITTED, grand_total}` |
| cancel | CANCEL | PURCHASE_REQUEST | `{status}` / `{status: CANCELLED}`, reason in `description` |
| item create | CREATE | PURCHASE_REQUEST_ITEM | – / full row incl. `specifications` |
| item patch / pricing | UPDATE | PURCHASE_REQUEST_ITEM | changed fields before / after |
| item delete | DELETE | PURCHASE_REQUEST_ITEM | full row / – |
| pre-invoice DRAFT created | CREATE | PRE_INVOICE | – / allowlisted summary (§ 26.9) |
| pre-invoice issued | ISSUE | PRE_INVOICE | `{status: DRAFT}` / `{status: ISSUED, pre_invoice_number, version, grand_total, supersedes_id}` |
| previous document replaced | SUPERSEDE | PRE_INVOICE (the old one) | `{status: ISSUED}` / `{status: SUPERSEDED, superseded_by_id}` — same transaction as the issue of the replacement |
| pre-invoice cancelled | CANCEL | PRE_INVOICE | `{status}` / `{status: CANCELLED, …}`, reason in `description` |
| PDF stored | PDF_GENERATE | PRE_INVOICE | – / `{pdf_status: ready, pdf_size, pdf_sha256, template_version, attempt_count}` — same transaction as the stored bytes |
| PDF failed | PDF_FAIL | PRE_INVOICE | – / `{pdf_status: failed, error_code, attempt_count}` — **best-effort** (a failure to write this row never undoes the recorded failure) |

Never in audit data: `password_hash`, any token or token hash, passwords. Token refresh is not audited. **Failed logins are not audited** (the organization/user may not exist, and `audit_logs.organization_id` is mandatory); they go to the application log [D4].

`GET /audit-logs` (ADMIN): filters `entity_type`, `entity_id`, `actor_id` (`user_id`), `action`, `created_from`, `created_to`; sort `created_at DESC, id DESC`. Read-only; no write endpoint exists.

## 14. Concurrency and idempotency rules

1. **One HTTP request = one database transaction** (default `READ COMMITTED`). Audit rows are in it.
2. **Lock order for every write on a request or its items:** first `SELECT … FROM purchase_requests WHERE id = :id AND organization_id = :org FOR UPDATE`, then check status/ownership, then write. This is the same lock mode the database triggers use, so concurrent writers queue instead of deadlocking (verified by `tests/concurrency.sh`: 12 writers × 10 inserts on one draft, no deadlock).
3. **Submit/cancel vs item writes:** whoever takes the lock second sees the new status and gets `409 STATE_CONFLICT`. An item can never slip in after submit.
4. **Request creation:** the counter row stays locked until commit; creations in the same organization and series serialize briefly and numbers are unique; a failed creation gives its number back.
5. **Optimistic check [D7] — applies to every `PATCH` (customer, product, request, item) and to `POST …/pricing`:** the body must carry the `updated_at` the client last read. If it differs from the stored value → `409 STALE_UPDATE` and the current resource in `details.current`. (Item writes bump the parent's `updated_at`, so pricing/patch on the request notice concurrent item edits.)
6. **No idempotency keys in Slice 01** (ADR-045 is Phase 2). A repeated `POST /purchase-requests` creates a second draft; the client must disable the button while a call is in flight. Repeated `submit`/`cancel` return `409`, never a false success.
7. A PostgreSQL deadlock/serialization failure (`40P01`, `40001`) is retried once by the Service; if it fails again → `503 TEMPORARILY_UNAVAILABLE`.
8. **Pre-invoice writes (§ 26):** lock order is always request header → replaced pre-invoice (if any) → number counter (first version only) → the pre-invoice row. PDF generation is the one exception to "one request = one transaction": it is three steps (count the attempt and commit; render with no transaction open; store the result), so a slow renderer never holds a lock.

## 15. Error codes → HTTP

Clients key off `code`; `message` is a human-readable English default (localization is the client's job). `details` is always present (object or array, possibly empty).

| HTTP | `code` | When |
|---:|---|---|
| 400 | `MALFORMED_REQUEST` | body is not valid JSON / wrong content type |
| 401 | `AUTH_INVALID_CREDENTIALS` | login failed (any reason) |
| 401 | `AUTH_TOKEN_INVALID` | access token missing/expired/invalid, or user/role/organization inactive |
| 401 | `AUTH_REFRESH_INVALID` | refresh token unknown, expired, revoked or reused |
| 403 | `FORBIDDEN_ROLE` | role lacks the capability (§ 4) |
| 403 | `FORBIDDEN_NOT_OWNER` | SALES acting on another user's request |
| 404 | `NOT_FOUND` (`details.resource`) | missing **or in another organization** |
| 409 | `STATE_CONFLICT` | illegal transition / frozen request / submit or cancel repeated (PostgreSQL `55000`) |
| 409 | `STALE_UPDATE` | `updated_at` mismatch (§ 14.5) |
| 409 | `DUPLICATE_IDENTIFIER` | customer `national_id`/`economic_code` (`23505`) |
| 409 | `DUPLICATE_RESOURCE` | product `code`/`name`, other unique violations (`23505`), incl. a second active pre-invoice for a request or chain (`details.reason`) |
| 422 | `VALIDATION_ERROR` | schema/format errors; `details: [{field, reason}]` |
| 422 | `INVALID_MONEY` | money/quantity format (§ 10) |
| 422 | `AMOUNT_OUT_OF_RANGE` | overflow, discount above gross, negative line total (`22003`, `23514`) |
| 422 | `INACTIVE_REFERENCE` | inactive customer/product/unit/category |
| 422 | `REFERENCE_NOT_FOUND` | id of a customer/product/unit/category that doesn't exist in the organization (body references; `23503`) |
| 422 | `SPECIFICATION_INVALID` | § 12 |
| 422 | `SUBMIT_PRECONDITION_FAILED` | § 8 |
| 429 | `RATE_LIMITED` | § 3; also PDF retry refused by the attempt policy (§ 26.7), `details.retry_after` |
| 500 | `PDF_GENERATION_FAILED` | the PDF could not be produced or stored (§ 26.7); the commercial state of the pre-invoice is unaffected; `details.error_code` is a closed code |
| 500 | `INTERNAL_ERROR` | unexpected; details never leak SQL or stack traces |
| 503 | `TEMPORARILY_UNAVAILABLE` | database unavailable / retry exhausted |

Unmapped PostgreSQL errors are `500`, logged with the `request_id`, never echoed.

## 16. Out of Slice 01

Pre-Invoice (MVP+1, ADR-060) · Revision/versioning · deleting a request (even a draft) · **creating or editing** categories / units / specification templates, fields and product specification values via API (reading categories and units is in, ADR-063) · user, role, password-reset and organization management · a configurable permission model (Permission tables, per-user grants) — the fixed three-role policy of § 4 **is** implemented in the Service · multi-organization users · payment condition, destination, transport, vehicle/driver, attachments, PDF/print/share · approval, payment, credit, inventory, loading, weighbridge, release, delivery · discount percentage/type, price sources, tax engine, freight · idempotency keys · shared rate-limit store · failed-login audit · reports/export · notifications · offline sync · Jalali values in the API · `ADR-FUTURE` items.

## 17. Optimistic concurrency payloads

`updated_at` in a request body is the exact string last returned by the API. The Service compares it to the stored `updated_at` at microsecond precision, after taking the lock of § 14.2.

## 18. Acceptance tests (Slice 01 is done only when all pass)

Real PostgreSQL 16 with 001 + 002 + 003 applied; real HTTP calls through the FastAPI app; no mocks of the database.

| ID | Area | Must prove |
|---|---|---|
| T-AUTH | auth | login OK / every failure reason returns the same 401 and similar timing; refresh rotation; reuse revokes all; logout; inactive user/role/org rejected on the next call; rate limit |
| T-TENANT | isolation | **(a) path resources:** every `GET/PATCH/DELETE/POST` addressed by a path id of organization B returns `404 NOT_FOUND` for a token of A, identical to a non-existent id. **(b) body references** (`customer_id`, `product_id`, `unit_id`, `category_id`, `default_unit_id`, `field_id`): an id of organization B and a random non-existent id produce the **same** response (`422 REFERENCE_NOT_FOUND`, same `details` shape) — existence is never revealed. (c) `organization_id` in any body is rejected; list endpoints never show B |
| T-ROLE | authorization | the full matrix of § 4, table-driven |
| T-CUST | customer | create/patch; digits normalization (`"۱۲۳ ۴۵"` → `"12345"`); empty → null; duplicate identifier → 409; same name allowed; filters |
| T-PROD | product | create/patch; duplicate code **and** duplicate name → 409; inactive category/unit → 422; specifications endpoint returns applicable fields only |
| T-SPEC | specifications | every case listed at the end of § 12; snapshot unchanged after the field's name/options are changed in the database; required-field check at submit; snapshot written exactly as the database trigger expects |
| T-MONEY | money | `"125000.00"`, JSON numbers, negatives → `INVALID_MONEY`; 6000-case cross-check of the Service function against PostgreSQL = 0 mismatches; overflow → `AMOUNT_OUT_OF_RANGE`; header totals read back equal the sum of items |
| T-NUM | numbering | `1405-000001` format; sequence per organization and per series; 20 parallel creations × 25 → 500 unique numbers; rollback gives the number back; Jalali-year selection at the Nowruz boundary (cross-checked against an independent implementation) |
| T-STATE | state machine | all 9 transitions (allowed and refused) via the API; frozen header and items after submit and after cancel; `409` mapping of `55000`; cancel from DRAFT and SUBMITTED; repeat submit/cancel → 409 |
| T-RACE | concurrency | submit racing 10 item inserts: no item after submit, no deadlock; two stale PATCHes → one `STALE_UPDATE`; same-request parallel item inserts keep totals correct |
| T-AUDIT | audit | each row of the § 13 table exists with correct action/entity/old/new; written in the same transaction (forced failure leaves neither change nor audit); no secrets in any audit row; direct UPDATE/DELETE on `audit_logs` still refused; enums reject unknown strings |
| T-ERR | errors | every code in § 15 is reachable and returns the documented HTTP status and envelope; no SQL text in any error body |
| T-ORG003 | migration 003 | backfill unique and deterministic on a DB that already has organizations; `ORG-001` vs `org-001` collide; code immutable; username CHECK; runner order |
| T-REFRESH | tokens | 20 concurrent refreshes of one token → exactly one `200`, 19 × `401 ALREADY_ROTATED`, **the winner's new refresh token and access token still work afterwards**, no token of the user was revoked by the race; reuse after the grace window (window configurable in tests) → `INVALID` and all the user's refresh tokens revoked; logout with another user's token → 401 and that token stays valid |
| T-CAP | limits | `bundle_count` 18 digits ✓ / 19 ✗; quantity/weight/money boundary values and overflow |
| T-PATCH | optimistic | every PATCH (customer, product, request, item) and pricing with a stale `updated_at` → `409 STALE_UPDATE`; every effective change returns a **new** `updated_at` (a no-op PATCH may keep it); item writes bump the parent's `updated_at`; request notes in SUBMITTED and CANCELLED → `409 STATE_CONFLICT` |
| T-LOOKUP | lookups | categories/units: org scoped, `is_active` default, all roles allowed |
| T-SEED | seeds | `998` then `999` in the runner's real order, twice each, on (1) an empty database, (2) a database seeded by the **old** 999 and then upgraded through 003 (legacy path: org becomes `DEMO`, `admin` gets a working hash), (3) a database where `admin`'s password was changed — the changed hash must survive; (4) a database with a **real organization named `TradeFlow Demo`** (other `national_id`) and no demo organization → 998 aborts with the clear error, the real organization and everything attached to it is byte-for-byte unchanged, no sample data appears anywhere, 999 does not run; (5) real same-name organization **and** a proper demo organization → abort, nothing changed; no duplicate rows anywhere in (1)–(3); dev login works in (1) and (2) |
| T-E2E | slice | the full path: login → customer → product → request with 2 items and specifications → pricing → save → retrieve → submit → audit list → cancel |

## 19. Known limitations accepted for Slice 01

In-process rate limiting (exactly one worker, § 3); no password reset; no user management API; master data loaded by seed; `field_id`-based specification input needs the client to call `GET …/specifications` first; creating a draft twice by double-click is possible if the client doesn't block it.

## 20. Decisions (all Accepted 2026-10-10 — § 24)

| # | Decision (proposed by the drafter unless stated) | Alternative |
|---|---|---|
| **D1** | Request number `YYYY-NNNNNN`, Jalali year in Asia/Tehran, restarts yearly. *(your proposal)* | one never-resetting series |
| **D2/D15** | Categories, units, templates, fields, product spec values are **seeded**, not API-managed; two **read-only** lookups `GET /product-categories` and `GET /units` are added (ADR-063, scope change); item `unit_id` defaults to the product's default unit. | seeded UUIDs documented, no lookups |
| **D3** | *Applicable* fields = active fields of active templates with `category_id` = product's category (no inheritance from parent categories, templates without category apply to nothing); `options` = array of strings. | inherit from parents; `{value,label}` objects |
| **D4** | Audit action set = your six + `LOGOUT`; entity set of 5; enums in code only (no DB CHECK, reason in § 3.1); failed logins not audited. | CHECK in 003; separate failed-login table |
| **D5** | Roles `ADMIN`/`SALES`/`ACCOUNTING` with the matrix of § 4; SALES writes only own requests. | SALES may edit any request; or ACCOUNTING may read audit |
| **D6** | Submit requires ≥ 1 item, every `unit_price > 0`, all required specification fields present, active references. | allow zero-price items; check required specs at save time |
| **D7** | Optimistic concurrency with `updated_at` on **all** PATCHes and pricing. | last write wins on master data |
| **D8** | Cancel requires a `reason` (1–500 chars), stored in audit `description`. | optional |
| **D9** | No content edit of any kind (notes included) in `SUBMITTED` **and** `CANCELLED` via the API (stricter than the database). | allow notes edits after submit |
| **D10** | JWT HS256 1 h; opaque refresh 30 d, rotation under row lock, **duplicate-tolerant policy with a 10 s grace window** (§ 3), real reuse revokes all; logout revokes own refresh token only and the access JWT lives until `exp`; argon2id; 10 failures / 15 min in-process limiter; usernames trimmed + lower-case. | other lifetimes / `jti` deny-list |
| **D11** | Dev seed `998_dev_seed_auth.sql` is **self-sufficient and upgrade-safe**: the runner applies seeds in numeric order, so 998 runs *before* 999 and cannot rely on it. 998 creates, idempotently and with the **same natural keys** as 999 (organization name `TradeFlow Demo`, role/unit/category/product codes, customer name, username `admin`), the organization (with `code = 'DEMO'`), roles, units, category, product, customer, one real-hash user per role, and a specification template with fields. 999 then finds everything present and inserts nothing. **Same-name guard (hard precondition, evaluated first):** let *N* be the set of organizations whose `name = 'TradeFlow Demo'`. 998 proceeds only if *N* is empty (it then creates the demo organization with `national_id = 'DEMO-NATIONAL-ID'`, `code = 'DEMO'`) or *N* is exactly one organization whose `national_id = 'DEMO-NATIONAL-ID'`. In **any other case** (a real organization shares the name; or several share it) 998 raises an exception with a clear message and changes nothing — the runner aborts the seed step, so 999 never runs in that invocation. Reason: the frozen 999 selects its target by name only, so it would otherwise attach sample roles, units, products, customers and an `admin` user to the real organization. 998 identifies the demo organization by the full natural key (name **and** `national_id`) everywhere. (Running `psql -f 999` by hand bypasses this guard; seeds are development tools and are refused in production by the runner.) **Existing, already-seeded databases:** the old demo organization already holds `DEMO` (003 backfill rule a) and is matched by name + `national_id`; 998 changes the `admin` user's password hash **only if it is still exactly `TEMPORARY_PASSWORD_HASH`**, and never overwrites any other hash (a changed password survives every re-run); it never touches other users' data. **Consequence:** after 003 (`code NOT NULL`) the frozen `999_dev_seed.sql` can no longer create an organization by itself; it works only after 998 (always true under the runner, not for `psql -f 999`). The frozen file is not edited. | edit 999 (breaks the freeze) |
| **D12** | No API to delete a draft request (cancel instead), although the database allows it. | add `DELETE /purchase-requests/{id}` (scope change → ADR) |
| **D13** | An item's `product_id` cannot be changed (delete + add). | allow, re-snapshotting specifications |
| **D16** | `organizations.code`: stored upper-case, format CHECK, plain UNIQUE, backfill with the explicit `DEMO` exception for the old seeded organization then `ORG-000001…`, immutable (§ 3.1). | free-form code with a case-insensitive unique index |
| **D17** | `users.username` stored trimmed + lower-case, enforced by CHECK in 003. | case-sensitive usernames |
| **D14** | `POST …/pricing` is a batch convenience over item price fields; one audit `UPDATE` per changed item. | single audit row for the batch |

Also pending from earlier reports, unchanged: the obsolete check 12 of `verify_round3.py`, and the real-`psycopg` Final Environment Verification run.

## 21. Review round 1 — disposition

| Review point | Disposition |
|---|---|
| 1.1 `MULTI_SELECT` / `organization_id` not in SQL | **Not a defect** — present in the real 001 (§ 0.1); migrations now shipped for verification |
| 1.2 category/unit lookups | **Accepted** — ADR-063, two read-only endpoints (D2/D15) |
| 1.3 product name uniqueness | **Not a defect** — `uq_products_org_name` exists in 001 (§ 0.1); contract unchanged |
| 1.4 003 and org code | **Accepted** — § 3.1 (D16), plus username CHECK (D17) |
| endpoint count | **Accepted** — 29 = 27 + 2 (§ 1) |
| `bundle_count` | **Not a defect** — real type `NUMERIC(18,0)`; boundary test added (T-CAP) |
| D7 scope | **Accepted** — all PATCHes |
| notes in SUBMITTED/CANCELLED | **Accepted** — § 8, D9; WORKFLOW aligned |
| `request_id` | **Accepted** — mandatory in every response (§ 2) |
| T-TENANT vs `REFERENCE_NOT_FOUND` | **Accepted** — split (a)/(b)/(c) |
| RBAC wording | **Accepted** — § 16 |
| concurrent refresh, logout | **Accepted** — § 3 |
| D4 CHECK | **Considered, declined** with reason (§ 3.1) |
| D8 trim | **Accepted** |
| D11 seed order | **Accepted** — and a further consequence found: 999 cannot create an organization after 003 (D11) |
| new tests | **Accepted** — T-ORG003, T-REFRESH, T-CAP, T-PATCH, T-LOOKUP, T-SEED |

## 22. Review round 2 — disposition

| Point | Disposition |
|---|---|
| Blocker 1: upgrading an already-seeded database (org code `DEMO`, `admin` hash) | **Accepted** — § 3.1 backfill rule (a), D11 upgrade-safe rules, T-SEED legacy path |
| Blocker 2: 003 scope omitted the trigger | **Accepted** — § 3.1 lists exactly four items |
| D7 test of timestamp bump | **Accepted** — T-PATCH |
| Argon2 version/parameters pinned | **Accepted** — § 3 |
| Rate limiter needs exactly one worker | **Accepted** — § 3 |
| ADR-063 | was Proposed here; **Accepted 2026-10-10** (§ 24) |

## 23. Review round 3 — disposition

| Point | Disposition |
|---|---|
| Real organization named `TradeFlow Demo` vs the name-keyed frozen 999 | **Accepted** — 998 same-name guard with abort, full natural key, T-SEED cases (4) and (5); 999 stays frozen |
| Refresh race could revoke the winner's new token | **Accepted** — duplicate-tolerant policy chosen explicitly (§ 3, D10); T-REFRESH asserts the winner stays valid; client single-flight rule |
| `tradeflow_hardened.zip` hash not re-verifiable inside the docs ZIP | Noted — the archive is not bundled; its SHA-256 is recorded in `baseline_sql/SHA256SUMS` for comparison against your copy |

## 24. Approval record and implementation notes (v6)

**Approval (2026-10-10, formal decision of the project owner):** D1–D17 **Accepted** as written in § 20; ADR-063 **Accepted** (`GET /api/v1/product-categories`, `GET /api/v1/units`, read-only; endpoint count stays 29; no create/edit API for categories, units or templates). From here the contract is the basis; changes go through the contract first, not through code.

**Control added to D11 at approval:** when 998 finds an organization matching **both** natural keys (`name = 'TradeFlow Demo'` and `national_id = 'DEMO-NATIONAL-ID'`), its `code` must be `DEMO`; otherwise 998 aborts with a clear error and never tries to change the immutable code. (Implemented and tested: T-SEED D8.)

**Implemented in this step (database only — no FastAPI yet):**
| File | Role |
|---|---|
| `sql/003_org_code_and_username.sql` | the four items of § 3.1, nothing else |
| `sql/998_dev_seed_auth.sql` | D11 seed: guard, demo org `DEMO`, roles, units, category, product, customer, spec template + 3 fields + 1 product value, users `admin`/`sales`/`accounting` (dev password documented in the file header, argon2id t=3 m=65536 p=4) |
| `tests/test_003_998.sh`, `tests/test_runner_order.py` | real PostgreSQL 16 tests, 48 + 7 assertions |
| `tests/regression_post003.sql`, `tests/concurrency_post003.sh` | the frozen 002 tests with **one** change: organization fixtures now supply `code` (003 makes it NOT NULL) |

**Facts found while implementing (recorded, not decisions):**
1. After 003, every test or script that inserts into `organizations` must supply `code`. The frozen baseline test files are unchanged; the `_post003` copies are the ones valid on top of 003.
2. Seeds run under `psql -f` (no wrapping transaction) work too: 998 uses no temporary tables.
3. The dev hashes in 998 were produced with `cryptography`'s Argon2id (PHC format, pinned parameters) because `argon2-cffi` could not be installed in the build environment; the PHC string is standard and verifies with `argon2-cffi`. Verification with `argon2-cffi` itself is part of the first FastAPI test run.
4. Not yet done: the real-`psycopg` run of the runner (the build environment cannot install `psycopg`; runner *logic* is tested with the real `runner.py`, SQL is applied with `psql -1` in runner order).

## 25. Review round 4 — disposition (the reviewer examined v5; checked against v6/v7)

| # | Point | Disposition |
|---|---|---|
| A | Logout: `204`, no body; `request_id` in `X-Request-Id` | **Accepted** — § 3 (204 was already there; empty body and the header on every response now explicit) |
| B | Dates Gregorian; Persian digits → ASCII; Jalali only in the client | **Accepted** — § 2 calendar rule |
| C | Failed-login counter keyed by `(organization_code, username)` **without IP**; 10 / 15 min; `429` + `Retry-After` | **Not adopted — D10 stays in force; any change needs a separate explicit decision.** Analysis kept for that decision: § 3 (accepted as D10) currently keys by `(organization_code, username, client IP)`. Removing the IP stops a distributed attacker from multiplying attempts, but lets anyone lock a known user out for 15 min; with the IP kept, the lock-out only hits that IP, but a botnet is not slowed. Not changed until decided. |
| D | Delivery date: service rule + DB rule | **Accepted** — § 8 now states both, independent (DB rule already exists in 002 C1) |
| E | `bundle_count` with 19 digits → `422 VALIDATION_ERROR`, not `INVALID_MONEY` | **Accepted** — § 9 |
| F | DECIMAL regex `{1,12}` → `{1,18}` | **Rejected as proposed (technical).** `NUMERIC(18,6)` has 18 digits in total, 6 after the point, so at most **12** before it; `{1,18}` would let through values the database refuses (`22003`). § 12 keeps `^-?[0-9]{1,12}(\.[0-9]{1,6})?$`. (`NUMBER` stays `{1,18}`: 18 digits fit `BIGINT`.) |
| G | Audit failed logins when organization **and** user are identifiable (wrong password / inactive); never when not identifiable | **Not adopted — D4 stays in force; any change needs a separate explicit decision.** Analysis kept for that decision: Contradicts accepted D4 ("failed logins not audited") and § 13. Costs to weigh: an attacker can fill the append-only `audit_logs` (it cannot be pruned; 002 forbids UPDATE/DELETE/TRUNCATE) — the rate limiter bounds this to ≈10 rows / 15 min per key; benefit: a record of attacks on real accounts. If accepted: `action LOGIN`, `entity USER`, `entity_id` = user id, `organization_id` = the user's, `old_data null`, `new_data {}`, `description "login failed"`; the response stays the identical `401 AUTH_INVALID_CREDENTIALS`. |
| H | MVP_SCOPE § 9: D1–D17 recorded | **Accepted** — done |
| I, K | Addendum renamed `ADR_ADDENDUM_056-063.md`, title/status header aligned; README/Manifest/MVP_SCOPE references | **Accepted** — done |
| J | Manifest | **Accepted with a correction:** 003 and 998 are no longer "planned": they were written and tested on 2026-10-10 after the owner's approval, so the Manifest lists them as implemented (database step only) |
| — | Reviewer's premise "003/998 must not be written yet" | Superseded by the owner's formal approval (§ 24); the four protected files (001, 002, runner.py, 999) are byte-identical to the baseline (SHA-256 in `baseline_sql/SHA256SUMS`) |

## 26. Stage 4 — pre-invoice (ADR-057, ADR-060; migration `004_pre_invoices.sql`)

**Status of this section:** written together with the code of Stage 4. Every statement is tagged **[Implemented]** (code and migration exist; *not executed by the author — the owner runs the tests*), **[MVP policy]** (a decision of this slice that is deliberately not a permanent rule of the product), **[Configurable]** (can be changed without code) or **[Future]** (not built). No item is tagged [Configurable] today: **nothing in Stage 4 is configurable yet** and nothing here may be presented as ready for per-company configuration.

### 26.1 What it is
A pre-invoice is an immutable commercial snapshot (seller, customer, request header, items, money) made from a `SUBMITTED` purchase request, numbered and issued by ACCOUNTING/ADMIN, with a server-generated PDF whose status is independent of the commercial status. [Implemented]

### 26.2 Statuses and transitions [Implemented — Service and database (`trg_pre_invoices_guard`)]
`DRAFT → ISSUED | CANCELLED`, `ISSUED → SUPERSEDED | CANCELLED`. `SUPERSEDED` and `CANCELLED` are final. Anything else → `409 STATE_CONFLICT`. A pre-invoice is never deleted. A DRAFT has no number and no version and is **not editable**: to change it, cancel it and create a new DRAFT. [MVP policy]

### 26.3 Endpoints [Implemented]
| Method and path | Capability | Notes |
|---|---|---|
| `POST /purchase-requests/{id}/pre-invoices` | `pre_invoices:create` | body `{}` or `{"supersedes_id": uuid}`; source request must be `SUBMITTED`; `201` + the DRAFT |
| `GET /pre-invoices` | `pre_invoices:read` | filters `status`, `source_request_id`, `customer_id`, `created_from`, `created_to`, `search`, `page`, `page_size`; SALES sees only pre-invoices of requests they created |
| `GET /pre-invoices/{id}` | `pre_invoices:read` | detail with items and `pdf` metadata (never bytes) |
| `POST /pre-invoices/{id}/issue` | `pre_invoices:issue` | assigns number/version, creates the `pending` document row; `200` |
| `POST /pre-invoices/{id}/cancel` | `cancel_draft` or `cancel_issued` | body `{"reason"?}`; reason **optional for a DRAFT, required (`422`) for an ISSUED document**; 1–500 characters after trimming |
| `POST /pre-invoices/{id}/pdf` | `pre_invoices:pdf` | generate / retry; independent of issuing; `200` with the document metadata, or `500 PDF_GENERATION_FAILED` / `429 RATE_LIMITED` |
| `GET /pre-invoices/{id}/pdf` | `pre_invoices:read` | `application/pdf`, `ETag` = SHA-256, `Cache-Control: no-store`; `409 STATE_CONFLICT` (`details.reason = PDF_NOT_READY`) until the PDF is `ready` |

Ownership ("own") is `purchase_requests.created_by` of the **source request**, not the creator of the pre-invoice. A pre-invoice of another organization or of a request SALES does not own is reported as `403 FORBIDDEN_NOT_OWNER` (own request check) or `404 NOT_FOUND` (other organization). [Implemented]

### 26.4 Numbering [Implemented]
The number is assigned **only at issue**, from the existing counter table of ADR-057 with series `PI-<Jalali year of the issue instant, Asia/Tehran>` (example `PI-1405`); the stored number is `PI-1405-000001`. No new counter table and no DDL on the counter. The counter row stays locked until commit, so a failed issue gives its number back and concurrent issues never duplicate a number. The request numbering is unchanged.

### 26.5 Replacement and versions [MVP policy; mechanism Implemented]
A request in `SUBMITTED` is frozen (§ 8), so an ISSUED pre-invoice can never be edited in place. A correction is a **new `SUBMITTED` request**; `POST /purchase-requests/{new}/pre-invoices {"supersedes_id": old}` makes a DRAFT that points at the issued document. Issuing that DRAFT, in **one transaction**, marks the old one `SUPERSEDED`, gives the new one the **same number with `version + 1`**, and writes the `ISSUE` and `SUPERSEDE` audit rows. If issuing fails the old document stays `ISSUED`. Cancelling the old request is not required. Database backstops: one ISSUED per request, one ISSUED per chain, one live successor per document. Not decided and not enforced: whether the customer must stay the same across a replacement. [Future: in-place revision, per-company correction policies.]

### 26.6 Request cancel guard [Implemented in the Service]
While an ISSUED pre-invoice exists for a request, `POST /purchase-requests/{id}/cancel` → `409 STATE_CONFLICT`, `details.reason = ACTIVE_PRE_INVOICE`; checked under the request-header lock. **Limit:** migration `002` is frozen, so this is a Service rule, not a database rule — direct SQL can still cancel such a request.

### 26.7 PDF [Implemented, with one open blocker]
Document status `pending` / `ready` / `failed`, independent of the commercial status. A failure never rolls back an issue; retrying is separate from re-issuing; a `ready` document and its SHA-256 are never overwritten (also enforced by trigger); a document row exists only for an issued pre-invoice.
* **Size:** at most 10 MiB (service and CHECK). Stored size and SHA-256 must describe the stored bytes; bytes must start with `%PDF-`.
* **Attempt policy** (one definition, `core/tradeflow_core/pre_invoice.plan_attempt`): the first attempt of a document is the *initial* attempt — always allowed, not a retry. Every later attempt is a *retry*: at least **60 s** after the previous attempt, and at most **3 retries per fixed 15-minute window** (the window starts at its first retry; after 15 minutes the next retry opens a new window). So the first 15 minutes can hold 1 initial + 3 retries. A refused attempt → `429 RATE_LIMITED`, `details.retry_after` (seconds), nothing is counted. A `ready` document short-circuits (returned as is, no attempt).
* **Three steps** (no lock is held while rendering): count the attempt and commit; render; store the result. Success audit (`PDF_GENERATE`) is in the storing transaction; failure audit (`PDF_FAIL`) is best-effort and is written in a savepoint.
* **Error:** failure → `500 PDF_GENERATION_FAILED`, `details.error_code ∈ {PDF_RENDERER_UNAVAILABLE, PDF_RENDER_FAILED, PDF_TOO_LARGE, PDF_INVALID_OUTPUT}` and the document metadata; the pre-invoice itself is untouched and still `ISSUED`.
* **Blocker (owner decision needed):** no PDF library and no Persian/RTL font are approved or present. The Service takes an injectable renderer; the default `UnavailableRenderer` always fails with `PDF_RENDERER_UNAVAILABLE`. Until a library, a pinned version and a font are approved, **PDF generation does not work in production**; the contract, tables, limits, retry policy and download are in place and tested with a fake renderer.
* Not decided and not enforced: Jalali dates in the PDF; whether SALES may generate (today: ADMIN and ACCOUNTING generate; SALES may only download their own); how a PDF of a `SUPERSEDED`/`CANCELLED` document looks (the model contains the snapshot only, not the lifecycle status).

### 26.8 Snapshot [Implemented]
Copied once at DRAFT creation: seller (organization), customer (without `credit_limit`), request number/date/delivery date/notes, items (product and unit code/name, quantities, money, `specifications` JSON) and header totals. **No new tax/freight/discount/rounding logic:** amounts are copied; the database re-checks that items add up to the header totals and `grand_total = subtotal − discount + tax`. `specifications` is carried as the generic array of § 12; nothing iron-specific is in the core.

### 26.9 Audit [Implemented]
`ISSUE`, `SUPERSEDE`, `CANCEL` (and `CREATE` of the DRAFT) are written in the **same transaction** as the change. Payloads are built by `pre_invoice.audit_data`, an **allowlist** (id, status, number, version, source request id/number, chain/supersedes ids, grand total, PDF status/size/hash/template version/error code/attempt count). Customer data, seller data, notes and items are never audited; `FORBIDDEN_KEYS` of § 13 (credentials) is not enough for that, hence the allowlist. `AUDIT_READ` stays ADMIN-only.

### 26.10 Product principle — what is and is not a rule of the core
General product for ironmongers and later other trades. **Not** core rules and **not built**: validity period (e.g. 24 h), prepayment, manager approval, payment terms, printed/optional seller fields, company-specific workflow, trade-specific specification fields. [Future] There is no settings or workflow engine in Stage 4. Tenant isolation, integrity and history are not switchable. [Implemented]

### 26.11 Lock order and errors [Implemented]
Request header → replaced pre-invoice → counter (first version only) → pre-invoice row (§ 14.8). `409 STATE_CONFLICT` for illegal transitions and conflicting state (`details.reason` ∈ `SOURCE_NOT_SUBMITTED`, `ACTIVE_PRE_INVOICE_EXISTS`, `OPEN_DRAFT_EXISTS`, `NOT_ISSUED`, `PDF_NOT_READY`, `ACTIVE_PRE_INVOICE`); `409 DUPLICATE_RESOURCE` when a unique index is reached (`details.reason` ∈ `ACTIVE_PRE_INVOICE_EXISTS`, `OPEN_DRAFT_EXISTS`, `ALREADY_REPLACED`).

### 26.12 Verification status
Nothing in this section has been executed by its author: no test, migration or seed was run. See `core/TEST_STATUS.md`.
