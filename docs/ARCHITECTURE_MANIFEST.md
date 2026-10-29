# TradeFlow — Canonical Architecture Package

Baseline Hardened = 001 + 002 + runner (frozen; changes only by new migration + ADR).

## Canonical documents

1. ADR_FINAL.md — architecture decisions
2. ADR-FUTURE_FINAL.md — future decision register (historical record, shipped unchanged in `docs/`)
3. DATA_MODEL.md — canonical data/domain model
4. WORKFLOW.md — canonical business lifecycle
5. API_SPECIFICATION.md — canonical API contract
6. UI_UX_SPECIFICATION.md — canonical client/UI specification
7. 001_initial_mvp.sql — canonical initial database migration
8. 002_harden_mvp.sql — canonical hardening migration (ADR-061)
9. runner.py — canonical migration runner (ADR-056)
10. ADR_ADDENDUM_056-063.md — decisions for the executable baseline (also appended to ADR_FINAL.md)
11. ARCHITECTURE_REVIEW_FINAL.md — final reconciliation record (historical record, shipped unchanged in `docs/`)
12. SLICE_01_CONTRACT.md — approved contract of the first vertical slice (v7)
13. 003_org_code_and_username.sql — implemented and tested 2026-10-10 (database step of Slice 01; ADR-059)
14. 998_dev_seed_auth.sql — implemented and tested 2026-10-10 (dev seed, never in production)

## Canonical technology direction

```text
Flet Client
    ↓
FastAPI / Python
    ↓
PostgreSQL
```

## MVP vertical slice

```text
Login
→ Organization
→ Customer
→ Product
→ Purchase Request
→ Items
→ Price
→ Save
→ Retrieve
→ Audit
```

Stage 4 after the slice: Pre-Invoice as MVP+1 (ADR-060) — backend written (migration 004), not yet executed by its author.

## Full architectural lifecycle

```text
Purchase Request
→ Order
→ Pricing
→ Approval
→ Proforma
→ Preparation
→ Exit Document
→ Loading
→ Weighbridge
→ Release
→ Goods Exit
→ Actual Quantity/Weight
→ Discrepancy Control
→ Finalization
→ Accounting Integration
→ Official Accounting Document
```

## Non-negotiable boundaries

- Payment ≠ Release
- Goods Exit ≠ Final Accounting Invoice
- Proforma ≠ Final Accounting Invoice
- Estimated ≠ Actual
- TradeFlow ≠ Accounting Software
- Client ≠ Database
- UI ≠ Business Rule Authority

## Package rule

The documents in this package are the canonical working set. Older drafts may remain in the user's Library for historical reference, but implementation should use these canonical files unless an ADR explicitly supersedes them.
