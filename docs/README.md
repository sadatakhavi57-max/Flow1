# TradeFlow — Architecture and Database Package (Baseline Hardened)

This package contains the canonical architecture documents and the executable database baseline.

## Baseline Hardened (frozen)

The database baseline is **`001_initial_mvp.sql` + `002_harden_mvp.sql` + `runner.py`**, with its regression suite. It is frozen: it is changed only through a new migration (003 and later) and an ADR, and only when a new test proves a real defect. Decisions behind it: `ADR_ADDENDUM_056-063.md` (also appended to `ADR_FINAL.md`).

| File | Purpose |
|---|---|
| `001_initial_mvp.sql` | Initial schema: 15 tables, composite same-organization foreign keys, money/line-total checks, totals trigger. Registers itself as version 001. |
| `002_harden_mvp.sql` | Hardening proven by tests: delivery date as DATE, customer identity and identifier normalization, append-only audit, purchase-request state machine and freeze, item specification snapshot, request-number counter table. Adds table 16. |
| `999_dev_seed.sql` | Development/demo seed only. Never run in production. |
| `runner.py` | Migration runner (ADR-056). |
| `tests/` | `regression.sql`, `money_contract.py`, `concurrency.sh`, `test_runner.py`, `run_all.sh`, and a psql-backed `psycopg` stand-in (test only). |

## Migration runner contract (ADR-056)

- Files are `NNN_name.sql` in one folder (default: the folder of `runner.py`; override with `--migrations-dir` or `TRADEFLOW_MIGRATIONS_DIR`).
- Versions must be **001–999**. `000` and `1000+` are rejected.
- **001–899** are schema migrations: applied in order, once, each in its own transaction together with its registration and checksum in `schema_migrations`.
- **900–999** are development seeds: applied only with `--include-dev-seed`, idempotent, not recorded, refused when `TRADEFLOW_ENV` is `prod`/`production`.
- Applied migrations are immutable (checksum), may not disappear, and a new migration may not be older than the newest applied one.
- One runner at a time (PostgreSQL advisory lock).
- Requires a **UTF8** database.

```text
export DATABASE_URL=postgresql://user:pass@host:5432/tradeflow
python runner.py                        # schema only
python runner.py --include-dev-seed     # also seeds (development only)
```

## Tests

```text
tests/run_all.sh   # regression (66 behavioural checks), money contract (6000 cases),
                   # concurrency (counter / inserts / submit race), runner scenarios (35 checks)
```

Verification status: all steps passed against PostgreSQL 16. The runner tests were executed through a psql-backed stand-in for `psycopg` because the package index was blocked in that environment. **One run of `tests/run_all.sh` with the real `psycopg` driver is still pending ("Final Environment Verification")**; it is an environment check, not a design blocker.

## About `verify_round3.py`

`verify_round3.py` is a historical verifier of migration 001 only. Its check #12 (`customer_unique_org_name`) is **obsolete after 002** — migration 002 intentionally removes that constraint (ADR-061, C2). Do not use it as the baseline verifier; `tests/regression.sql` is. It needs a separate update step.

## Canonical documents

`MVP_SCOPE.md` (scope; wins on conflicts), `DATA_MODEL.md` (conceptual model + "MVP Physical Data Model" aligned with 001+002), `WORKFLOW.md`, `API_SPECIFICATION.md`, `UI_UX_SPECIFICATION.md`, `ADR_FINAL.md` (+ addendum 056–063), `ADR-FUTURE_FINAL.md`, `ARCHITECTURE_MANIFEST.md`, `ARCHITECTURE_REVIEW_FINAL.md`.

## Accepted decisions that are not yet implemented

- Login by `organization_code + username + password` (ADR-059): the database side is **done** — `003_org_code_and_username.sql` and the dev seed `998_dev_seed_auth.sql` exist and pass real PostgreSQL 16 tests (`tests/test_003_998.sh`); the API side is not implemented yet.
- Pre-Invoice — accepted as **MVP+1** (ADR-060); backend written as Stage 4 (migration 004), not yet executed by its author; no UI, no PDF renderer yet.

## Next steps

1. `SLICE_01_CONTRACT.md` v7: decisions D1–D17 and ADR-063 are **approved** (2026-10-10). Next: FastAPI → Service → Repository → PostgreSQL implementing it.
2. Service-layer tests for `specifications.value` against `data_type` at the first endpoint.
3. Final Environment Verification with real `psycopg`.
