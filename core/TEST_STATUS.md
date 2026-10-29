# What ran and what did not (2026-10-16, PostgreSQL 16 local, Python 3.13)

RAN and PASSED (unittest, from core/): test_inputs 12, test_money 14 (incl. 6200 cases against live PG), test_specs 16
(snapshot accepted by the real DB trigger), test_numbering 15, test_policy 19, test_auth 23, test_pg_integration 9 = 108 (earlier draft modules moved to _earlier_draft/, not part of the run).
DB side (earlier): test_003_998.sh 48 assertions, test_runner_order.py 7, regression_post003.sql 66, concurrency 500 unique numbers.

DID NOT RUN (not possible here): any FastAPI/HTTP test; real psycopg and the runner under psycopg; real PostgreSQL
`FOR UPDATE` refresh-token race (the in-memory store only simulates it); cross-verification with argon2-cffi (verified
against the RFC 9106 vector with `cryptography`); production-locale behaviour.
The money test proves correctness on tested inputs, not full PostgreSQL compatibility.

# Stage 4 (pre-invoice) - added in v14: WRITTEN, NOT RUN
No test, migration, seed or database operation of Stage 4 has been executed by its author. Nothing below may be read as a pass.
New/changed test files: core/tests/test_pre_invoice.py (pure logic), core/tests/test_pg_pre_invoice.py (migration 004 on real PostgreSQL),
api/tests/test_pre_invoices_http.py (HTTP + real DB, fake renderer); changed: core/tests/test_policy.py, core/tests/test_pg_integration.py
(audit count is now len(AuditAction) x len(AuditEntity)), core/tests/pg.py and api/tests/pg.py (004 in the default files), api/tests/support.py
(pdf_renderer argument), db/tests/test_runner_order.py (expects 001-004).
The earlier numbers above (108 etc.) are history of earlier stages and no longer describe the code base.
