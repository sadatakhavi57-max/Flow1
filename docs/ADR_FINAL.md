# TradeFlow - Architecture Decision Records (ADR)

> **FINAL:** This is the canonical ADR set for the current TradeFlow architecture review. `ADR.md` is retained as historical source material and is not the active decision source.

> **Baseline note:** ADR-056 … ADR-061 (appended at the end of this file) describe and freeze the executable baseline `001 + 002 + runner` ("Baseline Hardened"); ADR-062 (cancel) and ADR-063 (read-only lookups) extend the MVP scope. Earlier ADRs are not rewritten; the cross-reference table before ADR-056 shows where a later ADR realizes, narrows or clarifies an earlier one.

## Purpose

This document contains the canonical architectural decisions for TradeFlow.
It records decisions that materially affect architecture, data integrity, security, workflow, or long-term maintainability.
Detailed business rules belong in the relevant specification documents.

**Phase labels**
- **MVP**: required for the currently defined first vertical slice.
- **PHASE 2**: accepted architectural direction, intentionally outside the current MVP.
- **FUTURE**: architectural readiness only; implementation is deferred.

---

# ADR-001 - Cross-Platform Client

**Phase:** MVP

## Decision
Flet is the primary client framework. The client is implemented in Python and targets Windows, Android, iOS and Web where supported by the Flet toolchain. Direct Dart/Flutter application development is not required for the TradeFlow client.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-002 - Layered Architecture

**Phase:** MVP

## Decision
Client, application/domain, data and infrastructure responsibilities must remain separated. Critical business rules must not live only in UI code.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-003 - Hybrid Client-Server Architecture

**Phase:** MVP

## Decision
The system uses a Flet/Python client, API/backend boundary and PostgreSQL central database. Local storage/synchronization is supported where required and remains behind the client/data boundary.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-004 - PostgreSQL as Central Database

**Phase:** MVP

## Decision
PostgreSQL is the central relational database. Transactions, foreign keys, constraints, indexes and migrations are first-class mechanisms.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-005 - Relational Local Storage

**Phase:** PHASE 2

## Decision
Client local storage, when introduced, must use a relational technology suitable for Python/Flet clients. SQLite is the current neutral direction. Offline capability is not required for the first vertical slice.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-006 - API as Application Boundary

**Phase:** MVP

## Decision
Clients must never connect directly to PostgreSQL. The backend/API owns authentication, authorization, validation, business rules and audit enforcement.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-007 - Backend Technology: Python/FastAPI

**Phase:** MVP

## Decision
For the current implementation, Python with FastAPI and psycopg is the selected backend direction. The API contract remains framework-independent.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-008 - Generic Business Core

**Phase:** MVP

## Decision
Core entities and workflows must remain industry-independent; iron and steel is the first business scenario.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-009 - Configurable Product Specifications

**Phase:** MVP

## Decision
Industry-specific product characteristics use configurable templates and fields rather than hard-coded columns.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-010 - Configurable Forms

**Phase:** FUTURE

## Decision
Commercial forms should eventually be template-driven. This is not required for the first vertical slice.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-011 - Independent Transaction Status Domains

**Phase:** PHASE 2

## Decision
Order, approval, payment, inventory, shipment, loading, weighing, release, delivery and settlement statuses must remain conceptually independent.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-012 - Payment Does Not Equal Release

**Phase:** PHASE 2

## Decision
Payment completion never automatically authorizes physical release. Release is a separate controlled action.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-013 - Approval and Authorization

**Phase:** PHASE 2

## Decision
Sensitive actions require explicit backend-enforced authorization. Maker-checker is used where the risk profile requires separation.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-014 - Immutable Audit Trail

**Phase:** MVP

## Decision
Important actions must be auditable with actor, action, record, timestamp and relevant before/after information. Audit records are not casually editable.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-015 - No Physical Delete of Registered Transactions

**Phase:** PHASE 2

## Decision
Registered commercial records must not be physically deleted. Cancellation, reversal, archive or other controlled lifecycle actions are used instead.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-016 - Historical Integrity

**Phase:** MVP

## Decision
Transactional records must preserve values applicable at transaction time; later master-data changes must not silently rewrite history.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-017 - Pricing Traceability

**Phase:** MVP

## Decision
The effective transaction price, discount and relevant override information must be traceable. Advanced pricing engines are deferred.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-018 - Estimated and Actual Weight Are Distinct

**Phase:** PHASE 2

## Decision
Estimated and actual weights are separate values and must never overwrite each other.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-019 - Weighbridge Reconciliation and Configurable Tolerance

**Phase:** PHASE 2

## Decision
Origin/destination weighing, net calculations, discrepancies and configurable tolerance are separate capabilities.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-020 - Freight Traceability

**Phase:** PHASE 2

## Decision
Agreed freight and actual freight are stored separately so discrepancies can be investigated.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-021 - Documents and Evidence as First-Class Data

**Phase:** PHASE 2

## Decision
Documents and attachments are linked to business entities and transactions. Large binaries are kept outside transactional rows.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-022 - Messenger Independence

**Phase:** MVP

## Decision
WhatsApp, Bale and other messengers are communication channels. Core transactions remain independent of any messenger.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-023 - Persian RTL and Shamsi Presentation

**Phase:** MVP

## Decision
The client supports Persian RTL and Shamsi presentation while backend storage/API use interoperable machine-readable date/time values.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-024 - Multi-Tenant Organization Isolation

**Phase:** MVP

## Decision
Every tenant-scoped record and authorization path must enforce organization isolation. Cross-tenant access is denied by default.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-025 - Security by Design and Session Management

**Phase:** MVP

## Decision
Authentication, authorization, password/token handling, tenant isolation, input validation and audit are architectural requirements.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-026 - Financial Precision

**Phase:** MVP

## Decision
Financially significant values use decimal/integer-safe representations and explicit rounding rules. Floating-point money calculations are prohibited.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-027 - Reporting Separation

**Phase:** PHASE 2

## Decision
Reporting queries and KPI calculations are separated from presentation. Reports must respect permissions, tenant isolation and historical integrity.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-028 - Versioned Database Migrations

**Phase:** MVP

## Decision
Database changes use ordered, immutable migrations tracked in schema_migrations with integrity checking.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-029 - Pilot Before Scale

**Phase:** PHASE 2

## Decision
TradeFlow is validated through internal testing, controlled pilot and then broader release. Pilot feedback may change implementation but not silently bypass architecture review.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-030 - MVP Scope Control

**Phase:** MVP

## Decision
The current MVP is limited to the first vertical slice: authentication, organization, customer, product, product specifications, purchase request/items, pricing, persistence/retrieval and audit.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-031 - Accounting and Official-System Integration Boundary

**Phase:** MVP ARCHITECTURE / PHASE 2 IMPLEMENTATION

## Decision
TradeFlow does not replace official accounting, tax or trade systems. Future integrations occur through explicit integration boundaries.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-032 - Business Rules Over UI

**Phase:** MVP

## Decision
Critical business rules and authorization must be enforced in backend/domain layers, not merely by UI controls.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-033 - Inventory as a First-Class Domain

**Phase:** PHASE 2

## Decision
Inventory, reservation and ATP are separate domain capabilities and are not part of the first vertical slice.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-034 - Order Revision and Versioning

**Phase:** PHASE 2

## Decision
Material changes to registered transactions require traceable revisions or change records.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-035 - Partial Shipment and Backorder

**Phase:** PHASE 2

## Decision
Orders may eventually be fulfilled through multiple shipments and backorders.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-036 - Customer Credit Control

**Phase:** PHASE 2

## Decision
Credit limit, exposure, overdue amounts, guarantees and credit agreements are managed as a dedicated capability.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-037 - Release Authorization

**Phase:** PHASE 2

## Decision
Physical release is a controlled, auditable action with its own authorization record.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-038 - Reconciliation as a First-Class Capability

**Phase:** PHASE 2

## Decision
The system will reconcile related records such as order/payment, order/inventory, shipment/weighbridge and invoice/transaction.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-039 - Proof of Delivery, Claims and Returns

**Phase:** PHASE 2

## Decision
Delivery evidence, post-delivery claims and returns are independent processes linked to the originating transaction.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-040 - Exception, SLA and Work-Inbox Architecture

**Phase:** PHASE 2

## Decision
Operational exceptions, deadlines and user work items are modeled explicitly rather than hidden in notes or messages.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-041 - Configurable Master Data

**Phase:** PHASE 2

## Decision
Master data such as units, categories, products, customers, tax and other configurable references have explicit lifecycle and activation rules.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-042 - Currency, Tax, Cost and Margin Architecture

**Phase:** FUTURE

## Decision
The financial architecture remains extensible for multi-currency, tax definitions, cost components and margin analysis.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-043 - Observability

**Phase:** PHASE 2

## Decision
Application/API/database errors, performance and correlation IDs must be traceable as the system becomes operational.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-044 - Integration and Event Boundary

**Phase:** FUTURE

## Decision
External integrations and asynchronous events use an explicit integration/event boundary rather than coupling domain logic to external systems.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-045 - Idempotency

**Phase:** PHASE 2

## Decision
Sensitive commands and external callbacks must support idempotent processing where retries can otherwise duplicate effects.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-046 - Offline Synchronization and Conflict Resolution

**Phase:** FUTURE

## Decision
Offline workflows require explicit sync metadata, conflict detection, retry and reconciliation. They are not assumed merely because local storage exists.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-047 - Search, Import, Export and Duplicate Detection

**Phase:** PHASE 2

## Decision
Operational bulk and discovery capabilities are designed as separate services/features rather than embedded in core transaction logic.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-048 - Backup, Disaster Recovery and Data Retention

**Phase:** FUTURE

## Decision
Production deployments require tested backup/restore, retention and archival policies without destroying audit or legal history.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-049 - Feature Flags and Subscription Architecture

**Phase:** FUTURE

## Decision
Feature rollout and future Free/Paid plans must be possible without coupling subscription logic to core domain rules.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-050 - QR/Barcode, OCR and Geolocation Readiness

**Phase:** FUTURE

## Decision
These capabilities may be added later but must not force unnecessary MVP dependencies.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-051 - Client/API Version Compatibility

**Phase:** PHASE 2

## Decision
Client and API versions must be identifiable; breaking changes require explicit versioning, migration/deprecation strategy and compatibility planning.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-052 - Source of Truth and No Hidden Business Logic

**Phase:** MVP

## Decision
Each critical fact has one authoritative owner. Business rules must be documented, testable and not hidden inside UI, reports or ad-hoc SQL.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-053 - Testability as an Architectural Requirement

**Phase:** MVP

## Decision
Core domain/application behavior must be testable independently. API, permission, financial and regression tests are required as implementation matures.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-054 - Architecture Change Control

**Phase:** MVP

## Decision
Material architectural changes require impact review across affected specifications, data model, workflow, API, UI, security, reporting and existing data.

## Rationale
This decision keeps the architecture explicit, testable and consistent with the current TradeFlow foundation while preventing future capabilities from silently expanding the MVP.

---

# ADR-055 - Commercial Lifecycle and Accounting Integration Boundary

**Phase:** ARCHITECTURE / PHASE 2 IMPLEMENTATION

## Decision
TradeFlow is the system for commercial and operational execution of the transaction. Its lifecycle may extend from customer/request and order through proforma, preparation, loading, goods exit, actual quantity/weight verification and final commercial state. The accounting system of each organization remains the financial system of record for accounting documents and accounting entries.

TradeFlow must expose an explicit integration boundary so finalized commercial information can be transferred to the organization's accounting system. The integration must not assume a single accounting product.

The proforma, exit documents and weighbridge evidence must remain linked so the final actual quantity/weight and any discrepancy can be traced to the commercial transaction. A final invoice/accounting document may be issued or recorded in the accounting system according to that organization's process.

## Rationale
TradeFlow and accounting software solve related but different problems. TradeFlow needs to control the real commercial workflow and reconcile what was ordered, prepared and actually removed, while the organization's accounting system may already provide its own proforma, invoice and accounting-entry modules. Separating the systems prevents duplicated financial logic and allows different companies to connect different accounting products without redesigning the TradeFlow core.

---

## Canonical Scope Rule

The current MVP is the first executable vertical slice. Capabilities marked PHASE 2 or FUTURE must not be treated as MVP implementation requirements merely because their architectural direction is accepted.

## ADR Governance

- ADR numbers are stable identifiers after publication.
- New decisions use the next available number.
- A superseded decision is marked Superseded rather than silently rewritten.
- Duplicate concepts are merged into one canonical ADR.
- Detailed API, UI, workflow and data-model rules remain in their respective documents and are referenced rather than copied into ADRs.

---

## Cross-references to the Baseline (informational; no earlier ADR is changed)

| Earlier ADR | Relation to ADR-056 … 061 |
|---|---|
| ADR-014 Immutable Audit Trail | Realized in the MVP at database level: `audit_logs` is append-only (ADR-061, C4). |
| ADR-015 No Physical Delete of Registered Transactions | Labelled PHASE 2, but the baseline already enforces its core in the MVP: only a `DRAFT` request can be deleted; `SUBMITTED`/`CANCELLED` cannot (ADR-061, C5). Revision/versioning stays Phase 2 (ADR-034). |
| ADR-016 Historical Integrity | Realized for item specifications by the per-item snapshot (ADR-061, C6). |
| ADR-024 Multi-Tenant Isolation | Composite same-organization foreign keys (migration 001); login/token context in ADR-059. |
| ADR-026 Financial Precision | Made concrete by ADR-058 (whole Rial, `NUMERIC(20,0)`, `ROUND_HALF_UP`). |
| ADR-028 Versioned Database Migrations | Made concrete by ADR-056 (transaction boundary, version range 001–999, seeds 900–999). |
| ADR-030 MVP Scope Control | Scope amended by ADR-057 (16th table) and clarified by ADR-060 (Pre-Invoice = MVP+1, not Slice 1). |
| ADR-034 Order Revision and Versioning | Still Phase 2; until then a submitted request is frozen. |
| ADR-042 Currency, Tax, Cost and Margin | Still Future; the MVP fixes one currency scale (ADR-058). |
| ADR-055 Commercial Lifecycle | Pre-invoice scheduling decided by ADR-060. |


# ADR Addendum 056–063 — Baseline Hardened

> **Status of this file:** addendum to `ADR_FINAL.md` (ADR-001…055). Per ADR governance, new decisions take the next free numbers; append these sections to `ADR_FINAL.md` or keep the file next to it.
> **Baseline:** `tradeflow_hardened.zip` = `001_initial_mvp.sql` + `002_harden_mvp.sql` + corrected `runner.py` + regression suite (66 behavioural checks, 6000-case money contract, concurrency, 35 runner checks). These ADRs describe that baseline; they do not redesign it.
> **Not yet done:** the runner has been exercised only through a psql-backed stand-in for psycopg. One run with the real driver is a *Final Environment Verification* item, not a design blocker.

| ADR | Title | Status |
|---|---|---|
| 056 | Migration Runner Contract and Transaction Boundary | **Accepted** |
| 057 | Organization Request Number Counter | **Accepted** |
| 058 | Money and Rounding Contract | **Accepted** — Option A (whole Rial, `NUMERIC(20,0)`) |
| 059 | Multi-Organization Login | **Accepted** — Option A (organization code + username); migration `003` implemented and tested 2026-10-10 |
| 060 | Pre-Invoice Scope | **Accepted** — Option 2, MVP+1. **Stage 4 implementation written** (migration `004`, API, tests); **not yet executed by its author** — verified only after the owner's test run (contract § 26) |
| 061 | Hardened MVP Data-Integrity Contracts (migration 002) | **Accepted** |
| 062 | Purchase Request Cancel Endpoint in the MVP | **Accepted** |
| 063 | Read-only Lookup Endpoints for Categories and Units | **Accepted** (2026-10-10) |

---

# ADR-056 — Migration Runner Contract and Transaction Boundary

**Phase:** MVP · **Status:** Accepted · **Extends:** ADR-028

## Decision
1. **File naming.** `NNN_name.sql`, `NNN` at least three digits and **within 001–999**. `000` and `≥ 1000` are rejected; they are never reinterpreted as another class.
2. **Classes.** `001–899` are schema migrations. `900–999` are development seed files.
3. **Each migration is its own atomic unit.** Its SQL, and its row in `schema_migrations` (version, name, checksum), commit together in one transaction. The runner does *not* wrap the whole set of pending migrations in one transaction. If `003` fails, `001` and `002` stay applied; `003` leaves nothing behind.
4. **Forward-only.** The runner never rolls back committed migrations. A migration that failed never committed and may be corrected and re-run. A migration that has committed anywhere shared is immutable (checksum); corrections go into a *new* migration.
5. **Integrity checks before applying anything:** applied migration whose file is missing → refuse; name mismatch → refuse; checksum mismatch → refuse; a new migration numbered **below the newest applied one** (out-of-order) → refuse; duplicate version numbers (`001` vs `0001`) → refuse.
6. **One runner at a time.** A session-level PostgreSQL advisory lock is held for the whole run and released only after the last commit.
7. **Seeds.** Never applied by default. Applied only with `--include-dev-seed`, refused when `TRADEFLOW_ENV` is `production`/`prod`, never recorded in `schema_migrations`, and must be idempotent.
8. **Migration SQL must not contain `BEGIN`/`COMMIT`**, and must not use statements that cannot run inside a transaction (e.g. `CREATE INDEX CONCURRENTLY`). Such operations need their own ADR and mechanism.
9. **Defaults.** Migration folder = the folder containing `runner.py` (override `--migrations-dir` / `TRADEFLOW_MIGRATIONS_DIR`); connection from `--database-url` or `DATABASE_URL`.
10. **Encoding.** Databases are UTF8 (enforced by migration 002, see ADR-061).

## Rationale
The original runner held its lock until *after* the unlock call but before the connection committed, so two simultaneous runners could both try to apply `001`; it treated `999_dev_seed.sql` as a migration; it relied on `parents[2]` for its default folder; and a failure in a late migration rolled back everything, including migrations that had already been applied and verified.

## Alternatives considered
* *One transaction for the whole run.* Simple to explain, but a late failure discards verified work and makes “what is applied” depend on the run, not on the database. Rejected.
* *Down-migrations.* Rejected for MVP: they double the surface that must be tested and are rarely exercised before they are needed.

## Consequences
* Operators must treat a failed run as “fix and re-run”, not “restore”.
* Schema changes that need non-transactional statements are not possible until a separate mechanism exists.
* Seeds must be written to be re-runnable (`WHERE NOT EXISTS`).

## Evidence
`tests/test_runner.py`: 35 checks on a real PostgreSQL 16 (fresh DB, re-run, tampering, missing file, seed opt-in/idempotence/production guard, default folder, failing migration leaves no partial table, out-of-order, three concurrent runners → applied exactly once, name rules incl. `000`/`1000`/`899`/`900`). The same suite on the original runner: 18 of 32 checks failed.

## Documents to update
README (state the transaction boundary in one sentence), `ARCHITECTURE_MANIFEST` (runner entry), `ARCHITECTURE_REVIEW_FINAL` (runner conflict is resolved).

---

# ADR-057 — Organization Request Number Counter

**Phase:** MVP · **Status:** Accepted · **MVP scope amendment:** required (see below)

## Decision
* A table `organization_request_counters (organization_id, series, last_number, updated_at)` with primary key `(organization_id, series)`.
* A function `next_request_number(organization_id, series) → bigint` that increments atomically with `INSERT … ON CONFLICT … DO UPDATE … RETURNING`.
* Request numbers are **never** computed with `MAX(request_number) + 1`.
* The service calls the function **in the same transaction** that inserts the purchase request. A rolled-back request returns its number.
* `series` is chosen by the service (a Jalali year such as `1405` is the expected choice). The **textual format** of `request_number` (prefix, padding) is deliberately not decided here; `purchase_requests.request_number` remains unique per organization.

## Rationale
`MAX()+1` collides under concurrency. A counter row serialises exactly the thing that must be serialised and nothing else.

## Consequences
* Creation of requests is serialised per `(organization, series)` until commit. Acceptable for the stated volumes; revisit if one tenant writes many requests per second.
* Numbers are unique and increasing; they are **not guaranteed gap-free** if a DRAFT is later deleted.
* The counter table is the **sixteenth MVP table**. `MVP_SCOPE.md` §2 must list it (this ADR is the required justification under its change rule).

## Evidence
Regression: sequence 1,2,3; series independent; organizations independent. Concurrency: 20 sessions × 25 calls → 500 distinct numbers, no duplicates, `last_number = 500`.

## Documents to update
`MVP_SCOPE` (table list), `DATA_MODEL` (entity + rule), `API_SPECIFICATION` (number is server-generated and returned), `WORKFLOW` §5.1.

## Update — Stage 4 (pre-invoice numbers; no new decision, no new table)
* Pre-invoice numbers use the **same** table and function with the series `PI-<Jalali year of the issue instant>` (example `PI-1405`); the stored number is `PI-1405-000001`. **No new counter table and no DDL on the counter** (migration `004` does not touch it).
* The number is allocated **only at issue**, inside the issue transaction, after the request-header lock and before the pre-invoice row lock (contract § 14.8). A failed issue returns its number. A replacement version keeps the number of its chain and does not call the counter.
* Request numbering is unchanged (series without prefix). Status: **implemented in code, not yet executed by its author.**

---

# ADR-058 — Money and Rounding Contract

**Phase:** MVP · **Status:** Accepted · **Decision:** Option A

## Decision
* Stored unit: **Rial**. Type: `NUMERIC(20,0)` everywhere. Amounts are whole-Rial integers (`125000`, not `125000.00`).
* Python: `decimal.Decimal`, rounding `ROUND_HALF_UP`.
* `NUMERIC(20,2)` and per-organization scale are **not** part of the MVP. Per-organization scale/multi-currency stays with ADR-042 (Future).
* Column types in migration 001 stay unchanged.

## A. Contract (applies to the whole MVP)
1. Money is **never** a binary float. Python uses `decimal.Decimal` with an explicit context (precision ≥ 40) — not the process default.
2. Line formula: `line_total = ROUND_HALF_UP( quantity × unit_price − discount_amount + tax_amount )`, rounded to the currency's scale. `ROUND_HALF_UP` is PostgreSQL's `ROUND` for non-negative numerics. **Python's default (`ROUND_HALF_EVEN`) is forbidden.**
3. The database enforces the formula with an exact-equality CHECK and keeps `purchase_requests` totals equal to the sum of its lines (trigger + CHECK). The client may display; the server decides.
4. Column types stay as in migration 001 (`NUMERIC(20,0)`). Changing them requires a new ADR superseding this one.

## B. Options considered (for the record)
| Option | What changes | Notes |
|---|---|---|
| **A. Whole currency units (current).** `NUMERIC(20,0)` everywhere; API accepts integers only. | API examples (`"125000.00"`, `"0.00"`) must be corrected to integers. | Simplest; no sub-unit exists in everyday Rial pricing. `DATA_MODEL §51` (“currency and precision configurable”) is deferred. |
| **B. Two decimals.** `NUMERIC(20,2)`. | Migration `003` retypes 6 columns and the CHECK/trigger arithmetic; tests re-baselined. | Keeps the API examples; adds a scale the business may never use. |
| **C. Per-organization scale.** | Currency/scale table, scale-aware CHECK or application-only rounding. | Honours `DATA_MODEL §51`; largest change; belongs with multi-currency (ADR-042, FUTURE). |

**Chosen: A.** It is what is implemented and tested (6000 cases, 0 mismatches); ADR-042 already reserves C. The stored unit is Rial; any Toman display is a presentation concern of the UI and never changes stored values.

## Evidence
6000 randomly generated cases (including exact `.5` products): reference implementation vs PostgreSQL → **0 mismatches**; Python default `Decimal` rounding → **756 mismatches**. Within the schema's limits a 28-digit context is technically enough; the explicit context removes dependence on global state.

## Documents to update
`API_SPECIFICATION §17` (examples → integers), `DATA_MODEL §51`, `UI_UX §65`, `tests/money_contract.py` (stays as the contract test).

---

# ADR-059 — Multi-Organization Login

**Phase:** MVP · **Status:** Accepted · **Decision:** Option A · **Precedes:** first authentication endpoint

## Decision
* Login input: `organization_code`, `username`, `password`.
* New column `organizations.code`, `UNIQUE NOT NULL`, added by an **additive migration `003`**. Migration 003 was **not created when this ADR was accepted**; it was written together with the authentication contract of the first slice. 001, 002 and the runner stay frozen. **Update 2026-10-10:** migration 003 is now written and tested (`003_org_code_and_username.sql`; adds the column, backfill, format/unique constraints, immutability trigger and the username CHECK — contract § 3.1); 001, 002 and the runner are unchanged.
* In the MVP a user belongs to exactly one organization (`users.organization_id`). A membership model (Option B) is a possible later ADR and does not break this one.
* After login, the token carries `organization_id` as the context. Services must **never** accept `organization_id` from a request body or query.

## Problem (facts from the baseline)
* `users.organization_id` is a single column; `username` is unique **only within an organization** (`uq_users_org_username`).
* `POST /auth/login` receives only `username` and `password`, so the same username in two organizations is ambiguous.
* `GET /organizations` is documented as “organizations available to the user” (plural), but a user can belong to exactly one.
* `organizations` has no login-friendly identifier (no code/slug).

## Options
| Option | Schema | Login | Multi-org user |
|---|---|---|---|
| **A. Organization code + username.** | Additive migration: `organizations.code` (unique, not null for new rows). `users` unchanged. | `{organization_code, username, password}` | No (one org per user). `GET /organizations` returns the user's one organization. |
| **B. Global identity + membership.** | New `user_organizations (user_id, organization_id, role_id)`; `username`/email globally unique. | `{username, password}` then organization selection | Yes. Largest change; touches roles, tokens, FK design. |
| **C. Globally unique username, single org.** | Replace `uq_users_org_username` with a global unique. | `{username, password}` | No. Simplest; cross-company staff need separate accounts. |

**Chosen: A** — smallest additive change, keeps every tenant FK untouched, and Option B can be added later without breaking A.

## Rules that follow
* The access token carries `organization_id`; every query is organization-scoped from it, never from request bodies.
* Refresh tokens are bound to the same organization context.
* Brute-force controls (rate limit, lockout) and the password-hash algorithm are specified in the authentication endpoint's own design, not here.

## Documents to update
`DATA_MODEL` (User, Organization), `API_SPECIFICATION §4–5`, `UI_UX §6` (login screen fields), migration `003` if A.

---

# ADR-060 — Pre-Invoice Scope

**Phase:** MVP+1 · **Status:** Accepted · **Decision:** Option 2 · **Stage 4:** implementation written, not yet run by its author

## Decision
Pre-invoice is part of the product scope, issued as an **immutable snapshot** from a `SUBMITTED` purchase request, **after** the first vertical slice is complete and tested.

> **Status update — Stage 4.** After Slice 1 passed, the owner ordered the implementation. It is **written** (migration `004_pre_invoices.sql`, `core/tradeflow_core/pre_invoice.py`, the pre-invoice service and routes, tests, contract § 26) but **no test, migration or seed has been executed by its author**; it counts as verified only after the owner's run in Codespaces. Baseline files `001`, `002`, `003`, `runner.py`, `999` are unchanged.
>
> **Decided for the MVP (MVP policy, not permanent product rules):** statuses `DRAFT → ISSUED | CANCELLED`, `ISSUED → SUPERSEDED | CANCELLED` (the last two final); a DRAFT has no number and is not editable (cancel and recreate); number only at issue; an issued document is never edited — a correction is a **new `SUBMITTED` request** whose pre-invoice `supersedes` the old one, and the old one becomes `SUPERSEDED` only when the replacement is successfully issued (same number, version + 1); a request with an `ISSUED` pre-invoice cannot be cancelled through the request cancel route (Service rule — `002` is frozen); PDF stored in `pre_invoice_documents` with its own status (`pending/ready/failed`), 10 MiB cap, ≥ 60 s between retries and ≤ 3 retries per 15 minutes (initial attempt not counted as a retry), a failure never rolls back issuing.
>
> **Not core rules, not built, not configurable today:** validity period (e.g. 24 h), prepayment, manager approval, payment terms, printed seller fields, company-specific workflow. There is no settings or workflow engine. [Future]
>
> **Open blocker:** no PDF library or Persian/RTL font is approved; production PDF generation needs that decision (the renderer is injected; the default fails with `PDF_RENDERER_UNAVAILABLE`).

Slice 1 order: Login → Organization → Customer → Product → Purchase Request → Items → Price → Save → Retrieve → Audit. Then MVP+1: Pre-Invoice.

## Problem
The project's own goal is “purchase request → pre-invoice”. The canonical MVP stops at **save / retrieve / audit** of the purchase request: `MVP_SCOPE` lists no pre-invoice table or endpoint, and the request status set is only `DRAFT / SUBMITTED / CANCELLED`. Meanwhile `ADR-055` and `WORKFLOW §5.5` already define the proforma as **commercial evidence, distinct from an accounting invoice**, and `UI_UX §22` requires that an approved pre-invoice is never edited in place (a new version is created instead).

## Options
| Option | Meaning |
|---|---|
| **1. Keep it Phase 2.** | MVP ends at the submitted request. Honest to the current `MVP_SCOPE`, but the product cannot yet produce its main document. |
| **2. “MVP+1”: a minimal pre-invoice after the first vertical slice works.** | A pre-invoice is an **immutable snapshot** issued from a `SUBMITTED` request: header + lines copied (including the item specification snapshot), its own number series (via ADR-057), `version`, status `DRAFT → ISSUED → SUPERSEDED/CANCELLED`, server-side PDF. Changing an issued pre-invoice = a new version. Approval workflow stays out. |
| **3. Treat the submitted request as the pre-invoice.** | No new tables, but contradicts ADR-055 (proforma is its own evidence record) and prevents versioning. Not recommended. |

**Chosen: Option 2**, scheduled after the first vertical slice runs end to end, not interleaved with it.

## Required together when implementation starts
`MVP_SCOPE`, `DATA_MODEL`, SQL (new migration), `API_SPECIFICATION`, `WORKFLOW`, `UI_UX`, tests. A single table dropped into the schema without those would recreate the document drift this baseline just removed.

---

# ADR-061 — Hardened MVP Data-Integrity Contracts (migration 002)

**Phase:** MVP · **Status:** Accepted · **Implemented in:** `002_harden_mvp.sql` · **Verified by:** `tests/regression.sql` (66 checks)

| # | Contract | Enforced by |
|---|---|---|
| C0 | The database is **UTF8**; migration 002 refuses to run otherwise. | DO block |
| C1 | `requested_delivery_date` is a calendar **DATE** (business day in `Asia/Tehran`); it may equal the request's day. | column type + CHECK |
| C2 | Customer **name is not an identity** and is not unique. Identity = `national_id`, `economic_code` (unique per organization when present). | constraint dropped; partial unique indexes |
| C3 | `national_id` / `economic_code` are **normalised**: Persian and Arabic-Indic digits → ASCII, whitespace/ZWNJ/NBSP removed, empty → `NULL`. | trigger + CHECK back-stop |
| C4 | `audit_logs` is **append-only** (no UPDATE, DELETE, TRUNCATE). | triggers |
| C5 | Request state machine: `DRAFT → SUBMITTED | CANCELLED`, `SUBMITTED → CANCELLED`; nothing else. After DRAFT, items and commercial header fields (customer, dates, totals) are **frozen**; only a DRAFT request can be deleted. `request_number`, `organization_id`, `created_by`, `created_at` never change. `notes` stays editable (deliberate). | triggers (row lock on the parent, same mode as the totals trigger → no deadlocks) |
| C6 | Each item carries its own **specification snapshot** (`specifications` JSONB array of `{field_id, field_code, field_name, data_type, value}`), validated for shape, organization ownership, code/type match and uniqueness; later changes to templates, fields or product values never alter it. | CHECK + trigger |
| C7 | Request numbers come from ADR-057. | table + function |

## Not enforced here (by design)
* **Value vs `data_type`** of a specification (e.g. `"ABC"` for a `DECIMAL`) → Service/API layer (ADR-032). It must be covered by the first endpoint's tests: `DECIMAL`+`"ABC"` ✗, `"125.50"` ✓; `INTEGER`+`"10"` ✓, `"10.5"` ✗; `BOOLEAN`; `DATE`; `OPTION` valid/invalid; `TEXT`.
* Required-field completeness of a snapshot against the product's template → Service layer.

## Consequences
* A migration over data that collapses to duplicate identifiers after normalisation (e.g. `۱۲۳` and `123`) **fails loudly and rolls back**; such data must be reviewed before running 002 on a real database.
* A superuser can disable triggers; the CHECK back-stops (normalised identifiers, state-independent formulas) remain. Role design (application role without `TRIGGER`/superuser) belongs to deployment.
* The `Asia/Tehran` constant in C1 is a deliberate simplification; per-organization time zones are a future decision.

## Documents to update
`DATA_MODEL` (OrderItem `specification_values` → snapshot; state machine; counter), `API_SPECIFICATION §8–9` (states, `specifications`, frozen-state conflict errors → 409), `WORKFLOW §5.1–5.2`, `UI_UX §13–15, §49`.

---

# ADR-062 — Purchase Request Cancel Endpoint in the MVP

**Phase:** MVP · **Status:** Accepted · **Amends:** `MVP_SCOPE.md` § 3 (per its Change Rule)

## Decision
`POST /api/v1/purchase-requests/{id}/cancel` is part of the MVP and of Slice 01. It moves a request `DRAFT → CANCELLED` or `SUBMITTED → CANCELLED` and nothing else; `CANCELLED` is final. The MVP endpoint set becomes 27 endpoints.

## Rationale
Migration 002 (ADR-061, C5) already allows exactly these transitions and tells users that a submitted request cannot be edited or deleted — cancellation is the only way out. A system whose database permits a state that no API can reach is documented wrongly, not scoped correctly. `API_SPECIFICATION.md` § 8 already described the endpoint.

## Consequences
- The endpoint's details (required `reason`, authorization, audit `CANCEL`, error mapping) are defined in `SLICE_01_CONTRACT.md`.
- Still outside the MVP: deleting a draft through the API, revision of a submitted request.

## Documents to update
`MVP_SCOPE.md` (§ 3, § 9), `API_SPECIFICATION.md` (§ 25), `WORKFLOW.md` (already describes the transition), `UI_UX_SPECIFICATION.md` (Cancel action exists in the request screens).

---

# ADR-063 — Read-only Lookup Endpoints for Categories and Units

**Phase:** MVP · **Status:** Accepted (2026-10-10, together with D1–D17 of `SLICE_01_CONTRACT.md` § 20; history: Proposed in contract v3 → technically endorsed in review round 3 → formally Accepted) · **Amends:** `MVP_SCOPE.md` § 3

## Decision
Two read-only, organization-scoped endpoints join the MVP: `GET /api/v1/product-categories` and `GET /api/v1/units`. Creating or editing categories, units, specification templates/fields and product specification values stays outside the MVP (seed/admin SQL). The MVP endpoint set becomes 29.

## Rationale
Creating a product needs `category_id` and `default_unit_id`; entering an item may need another `unit_id`. Without a read path the client cannot learn the valid UUIDs except by hard-coding seed values, which differ per organization.

## Consequences
Read access for all three roles; default filter `is_active=true`. No write endpoint is implied.

## Documents to update
`MVP_SCOPE.md` (§ 3), `API_SPECIFICATION.md` (§ 25), `UI_UX_SPECIFICATION.md` (selectors), `SLICE_01_CONTRACT.md` (§ 1, § 7).

