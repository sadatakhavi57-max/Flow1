# TradeFlow — MVP Scope

## 1. Purpose

This document is the single source of truth for MVP scope. Other canonical documents must not contradict it.

## 1.1 Baseline

The executable baseline of this scope is **Baseline Hardened**: `001_initial_mvp.sql` + `002_harden_mvp.sql` + `runner.py` (ADR-056, ADR-061). It is frozen: it changes only through a new migration and an ADR. Accepted decisions that shape this scope: ADR-056 … ADR-063 (see `ADR_ADDENDUM_056-063.md`).

## 1.2 First vertical slice (Slice 1)

```text
Login → Organization → Customer → Product → Purchase Request → Items → Price → Save → Retrieve → Audit
```

Pre-Invoice is **not** part of Slice 1 (ADR-060). It is **Stage 4**, written after Slice 1 (§ 2.1, § 3.1); **not yet executed by its author** — verified only after the owner's test run.

## 2. MVP Tables

1. organizations
2. roles
3. users
4. customers
5. product_categories
6. units
7. products
8. product_specification_templates
9. product_specification_fields
10. product_specification_values
11. purchase_requests
12. purchase_request_items
13. audit_logs
14. refresh_tokens
15. schema_migrations (infrastructure table; written only by the migration runner)
16. organization_request_counters (added by migration 002, ADR-057)

### 2.1 Stage 4 tables (migration 004 — written, not yet executed by its author; ADR-060)

17. pre_invoices — immutable snapshot of a `SUBMITTED` request (seller, customer, request header, money), statuses `DRAFT / ISSUED / SUPERSEDED / CANCELLED`
18. pre_invoice_items — the snapshot of its items (incl. the `specifications` JSON)
19. pre_invoice_documents — the server-generated PDF (bytes, SHA-256, size, status `pending / ready / failed`)

The pre-invoice number uses the existing counter (ADR-057) with series `PI-<Jalali year>`; no counter table was added.

Schema change **implemented** (migration 003, tested 2026-10-10; the physical model in `DATA_MODEL.md` describes the state after 001+002): it adds `organizations.code` (`UNIQUE NOT NULL`) for login (ADR-059). It adds a column, not a table.

## 3. MVP Endpoints

Stage 4 adds 7 endpoints on top of the 29 (§ 3.1). The list below is Slice 1.

Exactly the endpoints currently defined in `API_SPECIFICATION.md` § 25 (29 endpoints: 27 including `cancel` (ADR-062), plus the 2 read-only lookups of ADR-063). Request/response details: `SLICE_01_CONTRACT.md`. Login takes `organization_code`, `username` and `password` (ADR-059); `GET /organizations` returns the single organization of the current user; `organization_id` is never accepted from a request body or query (it comes from the token).

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me

GET  /api/v1/organizations
GET  /api/v1/organizations/{id}

GET  /api/v1/customers
POST /api/v1/customers
GET  /api/v1/customers/{id}
PATCH /api/v1/customers/{id}

GET  /api/v1/products
POST /api/v1/products
GET  /api/v1/products/{id}
PATCH /api/v1/products/{id}
GET  /api/v1/products/{id}/specifications
GET  /api/v1/product-categories                (read-only, ADR-063)
GET  /api/v1/units                             (read-only, ADR-063)

GET  /api/v1/purchase-requests
POST /api/v1/purchase-requests
GET  /api/v1/purchase-requests/{id}
PATCH /api/v1/purchase-requests/{id}
POST /api/v1/purchase-requests/{id}/submit
POST /api/v1/purchase-requests/{id}/cancel      (ADR-062)

POST /api/v1/purchase-requests/{id}/items
PATCH /api/v1/purchase-request-items/{id}
DELETE /api/v1/purchase-request-items/{id}

POST /api/v1/purchase-requests/{id}/pricing
GET  /api/v1/purchase-requests/{id}/pricing

GET  /api/v1/audit-logs
```

## 4. MVP Screens

- Login
- Dashboard (minimal)
- Customer List / Detail / Create-Edit
- Product List / Detail / Create-Edit / Specifications
- Purchase Request List / Detail / Form / Item Entry / Pricing
- Audit Log List
- Settings (Organization only)

## 3.1 Stage 4 endpoints (written, not yet executed by their author)

```text
POST /api/v1/purchase-requests/{id}/pre-invoices
GET  /api/v1/pre-invoices
GET  /api/v1/pre-invoices/{id}
POST /api/v1/pre-invoices/{id}/issue
POST /api/v1/pre-invoices/{id}/cancel
POST /api/v1/pre-invoices/{id}/pdf
GET  /api/v1/pre-invoices/{id}/pdf
```

Contract: `SLICE_01_CONTRACT.md` § 26. **Implemented:** the table/endpoint/audit/PDF-storage mechanics. **MVP policy (decision of this slice, not a permanent rule):** DRAFT not editable; replacement only through a new `SUBMITTED` request; role split SALES(own)/ACCOUNTING/ADMIN. **Configurable today: nothing.** **Future:** validity period, prepayment, manager approval, payment terms, printed fields, per-company correction policy, in-place revision. **Blocker:** no PDF library / Persian font approved — PDF generation fails with `PDF_RENDERER_UNAVAILABLE` until the owner decides.

## 5. Explicitly NOT MVP

**Accepted for a later step, not in Slice 1:**

- Pre-Invoice — decision accepted as **MVP+1** (ADR-060); the backend (migration 004, 7 endpoints, PDF storage) is **written as Stage 4 and not yet executed by its author**. There is still **no screen** (UI_UX § 22) and no PDF renderer.

**Not MVP:**

- Payment
- Voucher
- Approval workflow
- Credit control
- Inventory / Reservation / ATP
- Shipment / Loading / Weighbridge / Release / Delivery / POD
- Dispute / Claim / Return
- Reconciliation
- Accounting connector implementation
- File / Document management subsystem
- Offline synchronization
- OCR / Geolocation / CRM
- Customer / Supplier portal
- Subscription / Feature flags
- Multi-currency implementation (MVP currency: whole Rial, `NUMERIC(20,0)`, ADR-058)
- Tax engine
- Cost / Margin analysis
- Advanced reporting
- Docker
- CI/CD
- ER / Sequence / State diagrams

## 6. Change Rule

Adding any item to MVP requires an ADR. Removing an item requires an ADR. Silent scope expansion is prohibited.

## 7. Reference Rule

Every canonical document must reference this file for scope decisions. Where any document conflicts with MVP_SCOPE.md, MVP_SCOPE.md wins.

## 8. Money Rule

Amounts are stored as whole Rial in `NUMERIC(20,0)`. Python uses `Decimal` with `ROUND_HALF_UP`. `NUMERIC(20,2)` and per-organization scale are not MVP (ADR-058).

## 9. Open Items

**Decisions D1–D17** of `SLICE_01_CONTRACT.md` § 20 (request number series, seeded master data + two read-only lookups, applicable-field rule, audit vocabulary, role matrix, submit rules, optimistic concurrency, cancel reason, content freeze, JWT/refresh/argon2id policy, self-sufficient dev seed 998, no draft-delete API, immutable item product, pricing batch, lookups, `organizations.code`, normalized usernames) are **Accepted** (2026-10-10), as is ADR-063. Review round 4 proposals C (failed-login counter without IP) and G (audit of failed logins) were **not adopted**: D10 and D4 stay in force (contract § 25).
