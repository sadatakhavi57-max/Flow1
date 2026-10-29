# TradeFlow Architecture Review - Final Resolution

## Status

Architecture review completed against the available TradeFlow foundation documents, including DATA_MODEL.md, UI_UX_SPECIFICATION.md, ADR_REVIEWED_V2.md, ADR-FUTURE.md, the current MVP migration and migration runner.

## Canonical decisions

1. Client: Flet/Python. Direct Dart/Flutter application development is not required.
2. Backend: Python/FastAPI.
3. Central database: PostgreSQL.
4. Client never connects directly to PostgreSQL.
5. Current MVP vertical slice:
   Login -> Organization -> Customer -> Product -> Purchase Request -> Items -> Price -> Save -> Retrieve -> Audit
6. Payment is not Release.
7. Goods Exit is not Final Invoice.
8. Proforma/history must not be overwritten by actual exit quantity/weight.
9. TradeFlow owns commercial/operational truth; each organization's accounting system remains the accounting/financial system of record.
10. Accounting integration is an architectural boundary now, but connector implementation is deferred to Phase 2.
11. Industry-specific behavior remains configurable; iron/steel is the first scenario.
12. Critical rules are enforced in backend/domain, not only UI.

## Resolved conflicts

### ADR technology conflict
Historical ADR.md still contains Flutter/Drift and Node/Laravel alternatives. These are superseded by the current ADR_FINAL.md decisions: Flet/Python + FastAPI + PostgreSQL.

### MVP scope conflict
The historical MVP definition included payment, voucher, transport, loading, weighing, release, delivery and dispute. This is too broad for the executable first slice. Those capabilities remain architectural/Phase 2 capabilities unless explicitly promoted later.

### Accounting boundary conflict
Accounting integration is not an MVP implementation dependency, but the boundary must exist in architecture now. The accounting product is not hard-coded into TradeFlow.

### Status conflict
The system must keep operational status domains independent. UI documentation explicitly preserves distinctions such as Payment != Release, Loading != Release, Estimated Weight != Actual Weight and Draft != Registered Transaction.

### Database tenant-integrity conflict
The MVP migration contained organization-scoped tables but purchase_request_items did not carry organization_id, allowing cross-organization references to depend too heavily on application logic. The corrected migration adds organization_id and composite same-organization foreign keys for request, product and unit.

### Migration runner conflict
The runner defaulted to a `migrations` directory while the canonical migration file is stored at project root. The corrected runner defaults to the project root.

### Migration arithmetic conflict
The original line_total check allowed any value up to the calculated amount. The corrected migration requires exact equality: quantity * unit_price - discount + tax.

## Files to treat as canonical

- ADR_FINAL.md
- DATA_MODEL.md
- UI_UX_SPECIFICATION.md
- 001_initial_mvp.sql (corrected copy)
- runner.py (corrected copy)

## Historical files

ADR.md, ADR_REVIEWED.md and ADR_REVIEWED_V2.md are review/history artifacts. Do not use them as the active architectural source once ADR_FINAL.md is adopted.

## Important implementation gate

Do not run the migration until the corrected SQL has been placed at the project root and the Python environment is 64-bit with a working psycopg/PostgreSQL connection.

## Remaining documentation limitation

The standalone WORKFLOW.md and API_SPECIFICATION.md files are not present in the current Library index. Their previously discussed content is reflected in the current architectural context, but they should be restored from the user's project workspace before implementation if exact historical wording or endpoint details are required. This is a documentation-retrieval limitation, not a reason to delay the architecture decisions above.
