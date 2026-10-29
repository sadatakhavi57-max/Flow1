# tradeflow_core — Slice 01 pure-Python core

Dependency-light business logic for Slice 01 (PyJWT + cryptography only). No FastAPI, no psycopg: the HTTP and
Repository layers are NOT here and must be added in an environment that can install `fastapi`, `psycopg[binary]`,
`argon2-cffi`, `httpx`.

Modules: errors (code→HTTP, PG error mapping), digits, money, specs (snapshot), jalali/jalali_astro/numbering,
authz (role matrix), state (state machine + submit checks), concurrency (updated_at), audit, passwords (argon2id),
ratelimit, tokens (JWT + refresh policy), inputs/customers/purchase_inputs/auth_inputs (input rules), config.

Run (from this directory; do not use `python -I`):

    ./run_tests.sh <db/sql dir> <docs/SLICE_01_CONTRACT.md>   # fails if any test is skipped

Without those two arguments / a running PostgreSQL, 16 tests skip (the run is then NOT complete). Plain discover:

    TF_SQL_DIR=<db/sql> TF_CONTRACT=<contract.md> python3 -m unittest discover -s tests -t . -v

Tests marked PG need a local PostgreSQL 16 reachable by `psql` as the current user. They CREATE/DROP databases named
`tf_core_*` — run only on a test server. Without PG they skip with a message.
