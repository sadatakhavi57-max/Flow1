# TradeFlow — Business Workflow Specification

**Status:** FINAL / Canonical — synchronized with Baseline Hardened (migrations 001 + 002) and ADR-056 … ADR-063
**Architecture:** Flet Client → FastAPI Backend → PostgreSQL
**Scope:** Industry-independent commercial transaction platform; iron/steel is the first business scenario.

## 1. Purpose

This document defines the canonical business lifecycle used by TradeFlow. It separates the commercial/operational truth managed by TradeFlow from the official accounting truth managed by the organization's accounting software.

TradeFlow must preserve historical evidence. A later operational fact must not silently rewrite an earlier commercial document.

## 2. Architectural Boundary

```text
Flet Client
    ↓
FastAPI API
    ↓
Application / Domain Services
    ↓
Repositories
    ↓
PostgreSQL

TradeFlow
    = commercial + operational truth

Accounting Software
    = accounting + official financial truth

Integration Layer
    = controlled bridge between the two
```

TradeFlow does not become the organization's accounting system merely because an invoice eventually references a TradeFlow transaction.

## 3. Canonical Lifecycle

```text
Purchase Request
      ↓
Order / Transaction Registration
      ↓
Pricing & Commercial Conditions
      ↓
Approval (where required)
      ↓
Proforma / Commercial Document
      ↓
Preparation / Availability
      ↓
Exit Document / Release Preparation
      ↓
Vehicle + Driver + Loading
      ↓
Origin Weighbridge
      ↓
Goods Exit / Release
      ↓
Document & Evidence Control
      ↓
Actual Product / Actual Quantity / Actual Weight
      ↓
Discrepancy Check
      ↓
Finalization
      ↓
Accounting Integration
      ↓
Official Accounting Invoice / Journal / Settlement
```

Not every transaction must use every stage. The applicable path is determined by business rules and transaction type.

## 4. Core Rules

### 4.1 Payment is not Release

Payment status and physical release authorization are independent.

```text
Payment = financial event/status
Release = physical authorization/status
```

Full payment alone must never cause an automatic release unless an explicit release rule independently authorizes it.

### 4.2 Goods Exit is not Final Invoice

A goods exit can occur before the final official invoice is issued. TradeFlow records the actual operational facts and later provides them to the accounting system.

### 4.3 Proforma is Historical Evidence

Once a proforma/commercial document is registered, its historical content must remain traceable. Later actual quantity/weight is recorded as an actual fact, not by silently overwriting the proforma.

Example:

```text
Proforma quantity: 20,000 kg
Actual exit quantity: 19,720 kg

Difference: 280 kg
```

The discrepancy is recorded and explained according to the applicable business rule.

### 4.4 Estimated and Actual Values are Separate

Estimated quantity, estimated weight, actual quantity, actual weight, packaging weight, empty/full vehicle weight and net weight must not be conflated.

### 4.5 Status Domains are Independent

Order, approval, payment, availability, voucher, loading, weighing, release, delivery and settlement are separate concepts. One status must not be used as a shortcut for another.

## 5. Stage Definitions

### 5.1 Purchase Request

The user creates a commercial request containing at minimum:

- Organization
- Customer / Party
- Product(s)
- Product specifications where applicable
- Quantity and unit
- Estimated weight where applicable
- Commercial notes
- Initial price information where permitted
- Attachments where applicable

The request may be saved as Draft before submission.

In the MVP the request has exactly three statuses and the transitions of § 15. Attachments are not part of the MVP (no file subsystem, see `MVP_SCOPE.md` § 5).

### 5.2 Order / Transaction

After acceptance of the request, the transaction receives a stable identity. Registered transaction history must remain auditable.

In the MVP, "registered" means `SUBMITTED`. The request already has a stable `id` and `request_number` from creation (the number comes from the per-organization counter, ADR-057).

Future order revision/versioning is a Phase 2 capability.

### 5.3 Pricing

Pricing records the commercial price and applicable discount/conditions with traceability to the actor and time of change.

Financial calculations use decimal-safe values. Floating-point arithmetic must not be used for money calculations.

MVP pricing (ADR-058): price information lives on the request items (`unit_price`, `discount_amount`, `tax_amount`, `line_total`) as whole Rial (`NUMERIC(20,0)`); `line_total = ROUND_HALF_UP(quantity × unit_price − discount_amount + tax_amount)`. Pricing can change only while the request is `DRAFT`; price changes are audited.

### 5.4 Approval

Where approval is required, the transaction enters an explicit approval state. Approval is an authorization event, not merely a UI button state.

The backend enforces permissions and authorization.

### 5.5 Proforma

A proforma is a commercial document/evidence record. It may contain planned quantities, prices, discounts, tax or other configured commercial values.

TradeFlow may store and reference the proforma as part of the operational dossier. The organization's accounting software remains authoritative for official accounting records where applicable.

MVP status (ADR-060): **Stage 4 is written** (migration 004, API, tests) and **not yet executed by its author**. It is not part of the Slice 1 vertical slice (§ 7).

Implemented flow (contract § 26):

```text
SUBMITTED request → POST …/pre-invoices → DRAFT (no number, not editable)
  → issue (ACCOUNTING/ADMIN): number PI-<year>-<n>, version 1, status ISSUED, pdf pending   [one transaction + audit]
  → POST …/pdf (separate): pdf ready | failed — never changes the commercial status
ISSUED → cancel (reason required) → CANCELLED
ISSUED → replaced by: a NEW SUBMITTED request → DRAFT with supersedes_id → issue
         → old = SUPERSEDED, new = ISSUED, same number, version + 1                          [one transaction]
DRAFT → cancel (reason optional) → CANCELLED; edit = cancel + new DRAFT
```

A request with an `ISSUED` pre-invoice cannot be cancelled by the normal request cancel (`409 STATE_CONFLICT`). Roles: SALES creates/cancels DRAFTs and views for **own** requests (`purchase_requests.created_by`); ACCOUNTING views, issues, cancels ISSUED, generates PDFs; ADMIN all.

**MVP policy, not permanent rules:** the replacement route and the role split above. **Not built (future):** validity period (e.g. 24 h), prepayment, manager approval, payment terms, company-specific workflow; there is no settings/workflow engine and nothing here is configurable yet.

### 5.6 Preparation / Availability

The transaction may move into preparation once the commercial conditions permit operational fulfillment.

Inventory/reservation/ATP are Phase 2 domains. The MVP does not implement full inventory control.

### 5.7 Exit Document

An exit document is an operational authorization/evidence record associated with the transaction. It is not automatically an accounting invoice.

### 5.8 Loading

Loading records the physical preparation of goods for dispatch. It may include:

- Transaction reference
- Product/item
- Quantity/bundle information
- Vehicle
- Driver
- Loading time
- Operator
- Attachments
- Notes

Loading completion does not by itself authorize release.

### 5.9 Weighbridge

Where weighing is used, TradeFlow records the evidence needed to establish actual weight.

Typical values:

- Empty vehicle weight
- Loaded vehicle weight
- Net weight
- Weighbridge ticket/reference
- Date/time
- Vehicle
- Related transaction

Destination weighing may later be recorded as a separate operational event.

### 5.10 Release

Release is a controlled authorization to physically allow goods to leave.

Release must evaluate the applicable business conditions and permissions. Payment status may be one input, but it is never equivalent to release authorization.

### 5.11 Goods Exit

The exit event records that goods physically left the organization's control.

The exit record must preserve the relationship to:

- Transaction/order
- Proforma/commercial document
- Loading record
- Weighbridge evidence
- Vehicle/driver
- Actual product and quantity/weight
- Release authorization
- Attachments

### 5.12 Actual Goods and Discrepancy

After loading/weighing/exit, actual facts are compared with planned/commercial values.

The system must record discrepancies explicitly rather than modifying historical planned values.

Possible discrepancy dimensions include:

- Product
- Specification
- Quantity
- Weight
- Packaging
- Vehicle
- Delivery destination
- Other configured operational values

Reconciliation rules are Phase 2.

### 5.13 Finalization

Finalization means the operational record has reached a stable controlled state for the applicable transaction path.

Finalization does not mean that the accounting system has necessarily posted the transaction.

### 5.14 Accounting Integration

After operational facts are controlled, TradeFlow exposes a standardized integration payload or connector operation.

The accounting system may then create its own official accounting documents, including its invoice/journal entries according to the organization's accounting process.

TradeFlow stores integration status/reference information where implemented, but does not duplicate accounting logic unnecessarily.

## 6. Exit Dossier

The complete operational evidence package is conceptually an **Exit Dossier** containing:

1. Order / Transaction
2. Proforma / Commercial Document
3. Exit Document
4. Loading Record
5. Weighbridge Ticket(s)
6. Actual Product
7. Actual Quantity / Weight
8. Vehicle
9. Driver
10. Attachments
11. Control Result
12. Discrepancy Record
13. Approval / Release Authorization
14. Finalization Result
15. Accounting Integration Reference, when applicable
16. Final Accounting Reference, when returned by the accounting system

The dossier is a logical business concept. It does not require one physical database table.

## 7. MVP Workflow

The first executable vertical slice is intentionally smaller:

```text
Login
  ↓
Organization
  ↓
Customer
  ↓
Product
  ↓
Purchase Request
  ↓
Items
  ↓
Price
  ↓
Save
  ↓
Retrieve
  ↓
Audit
```

The full lifecycle above is architectural scope, not MVP implementation scope. After "Audit" comes Pre-Invoice (MVP+1, ADR-060): Stage 4 backend written, not yet executed by its author.

## 8. MVP Rules

The MVP must support:

- Authentication/session
- Organization context
- Customer CRUD within organization permissions
- Product catalog
- Product specifications
- Purchase request creation
- Purchase request items
- Price information
- Draft/save/retrieve
- Status transitions `DRAFT → SUBMITTED | CANCELLED`, `SUBMITTED → CANCELLED` and the Freeze rule (§ 15)
- Server-generated request numbers
- Audit logging (append-only)
- Organization isolation
- Backend validation

The MVP must not silently grow to include the full logistics/accounting lifecycle.

## 9. Phase 2 Workflow Domains

Phase 2 may implement:

- Approval
- Payment
- Credit
- Voucher
- Inventory/reservation/ATP
- Transport
- Loading
- Weighbridge
- Release
- Delivery/POD
- Discrepancy/reconciliation
- Claims/returns
- Advanced documents
- Accounting connectors
- Advanced reporting

## 10. Error and Exception Principles

The system must never silently convert an exception into success.

Examples:

- Unauthorized release → rejected
- Cross-organization reference → rejected
- Inactive product in a new request → rejected
- Invalid customer → rejected
- Invalid price/discount → rejected
- Missing required evidence → blocked where the workflow requires it
- Weight discrepancy → recorded, not hidden
- Accounting integration failure → operational transaction remains identifiable; integration status records the failure/retry state when integration exists

## 11. Audit Requirements

Sensitive events must be auditable with at least:

- Organization
- Actor
- Action
- Entity/record
- Timestamp
- Relevant before/after data where appropriate
- Reason/comment where required

Audit history is historical evidence and must not be casually edited.

## 12. Source-of-Truth Rules

| Information | Primary authority |
|---|---|
| Commercial request | TradeFlow |
| Product catalog | TradeFlow |
| Commercial price history | TradeFlow |
| Operational loading | TradeFlow |
| Weighbridge operational evidence | TradeFlow, where configured |
| Physical release authorization | TradeFlow, where configured |
| Actual operational quantity/weight | TradeFlow, based on recorded evidence |
| Official accounting invoice | Accounting software |
| Accounting journal | Accounting software |
| Official financial ledger | Accounting software |

## 13. Terminology Rules

These terms must remain distinct:

- Payment ≠ Release
- Loading ≠ Release
- Release ≠ Delivery
- Delivery ≠ Settlement
- Proforma ≠ Final Accounting Invoice
- Estimated Weight ≠ Actual Weight
- Planned Quantity ≠ Actual Quantity
- TradeFlow Transaction ≠ Accounting Journal

## 14. Architectural Change Rule

If a future feature changes one of these boundaries, update the relevant ADR, DATA_MODEL, WORKFLOW, API specification and UI/UX specification before implementation.

## 15. Purchase Request State Machine (MVP, enforced by the database)

Source: migration `002_harden_mvp.sql`, ADR-061 (C5), tested in `tests/regression.sql`.

```text
DRAFT ──► SUBMITTED ──► CANCELLED
  └─────────────────────►┘
```

| From | To | Allowed |
|---|---|---|
| DRAFT | SUBMITTED | yes |
| DRAFT | CANCELLED | yes |
| SUBMITTED | CANCELLED | yes |
| any other (including CANCELLED → anything, SUBMITTED → DRAFT) | | no — rejected |

Rules:

1. **DRAFT** — fully editable: customer, delivery date, notes, items and prices. Physical deletion is allowed for a draft only.
2. **SUBMITTED / CANCELLED** — commercial content is frozen: customer, request date, delivery date, the four totals and every item (add, change, delete). At **database** level only `status`, `notes` and `updated_*` can still change; at **API** level (Slice 01 contract, D9) nothing is editable in these states — not even notes — and only `submit`/`cancel` act on the request. The request can never be deleted.
3. `organization_id`, `request_number`, `created_by` and `created_at` never change.
4. A change to a `SUBMITTED` request is not possible in the MVP. Revision/versioning is Phase 2 (ADR-034); until then the routes are cancel and create a new request.
5. The API maps violations to `409` (see `API_SPECIFICATION.md` § 13). Submit and item writes are race-safe: a concurrent submit cannot slip in an item after the freeze.
6. Every status change, price change and creation writes an audit record (service responsibility); audit records cannot be modified.

## 16. Request Numbering (ADR-057)

The number is allocated in the same transaction that creates the request, from a per-organization, per-series counter (`next_request_number`). Numbers are unique per series, never reused after commit, and given back if the creating transaction rolls back. `MAX()+1` is prohibited.

## 17. Business Rules Not Enforced by the Database

The service layer must enforce and test: active customer/product/unit when creating, validation of specification values against `data_type`, required specification fields, permissions, and creation of audit records. (See `DATA_MODEL.md`, "MVP Physical Data Model", § 6.)
