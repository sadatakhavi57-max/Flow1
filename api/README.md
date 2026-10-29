# api/ — Slice 01 HTTP + PostgreSQL layer (FastAPI, psycopg 3)

All 29 endpoints of the Slice 01 contract are written:
auth (4), organizations (2), customers (4), products (5), lookups (2), purchase requests (6), items (3), pricing (2), audit-logs (1).
Stage 4 adds 7 pre-invoice endpoints (app/pre_invoices_service.py, app/routes/pre_invoices.py; contract section 26).

Run (PostgreSQL 16 reachable by libpq as the current user; creates and DROPS database `tf_api_test`: TEST SERVER ONLY):

    python3 -m pip install -r api/requirements.txt
    ./api/run_tests.sh <path to db/sql>          # exit 0 = everything ran and passed; exit 3 = something was skipped

Layering: routes (app/routes/*.py, wired by main.py) -> *_service.py (policy: role check, ownership, optimistic check, audit; SQL inside) ->
pure rules in ../core/tradeflow_core.  One HTTP request = one transaction (db.run); refresh is the only place with
more than one transaction (the theft response must commit before the error is raised).

STATUS (honest): written where FastAPI/psycopg could not be run.
 * Stage 1 (auth) and stage 2 (customers, products, lookups, organizations): run by the owner in Codespaces, 37 passed
   (before the reviewer-driven hardening listed below was added).
 * Added after that and NOT yet run by anyone: content-type check, atomic login/logout+audit, 405 envelope, mobile
   search via normalize_identifier, tests/test_hardening_http.py, and ALL of stage 3
   (tests/test_requests_http.py, tests/test_requests_flow_http.py).
 * v13.1: main.py split into app/routes/{auth,master,requests,audit}.py - a behaviour-preserving move (the 29 method+path+status
   triples were compared mechanically with v13); NOT yet run: re-run all api tests.
 * Not done: pinning dependency versions (do it from a green `pip freeze`).
 * Stage 4 (v14): pre-invoices - migration 004, service, routes, request-cancel guard, tests/test_pre_invoices_http.py - WRITTEN, NOT RUN by
   its author. PDF generation needs an approved library/font: create_app(..., pdf_renderer=...) takes any object with render(model) -> bytes;
   the default renderer fails with PDF_RENDERER_UNAVAILABLE (tests use a fake renderer).
