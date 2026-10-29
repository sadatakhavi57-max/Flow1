# Integration notes - what is verified, what is not, what the next step must do

## 1. Verified here (real execution, this environment)
| Area | Evidence |
|---|---|
| Line total vs PostgreSQL | 6000 generated cases (incl. >1000 exact .5 ties): `money.compute_line_total` equals PostgreSQL's own `ROUND(q*p - d + t, 0)`, evaluated live in the same run. A guard test proves the set can tell HALF_UP from HALF_EVEN. Range decisions (`price_line` accepts/refuses) equal PostgreSQL's `NUMERIC(20,0)` overflow behaviour on 400 cases. 150 items inserted with Service-computed totals: all CHECKs pass and the trigger's header totals equal `check_header_totals_fit`. |
| Snapshot vs trigger | A snapshot built from the seeded fields is accepted by the real trigger of migration 002 and stored verbatim; malformed snapshots are refused with 23503/23514. |
| Jalali year | Three references agree: my implementation vs ICU (Node `Intl`, every day 1900-2099), vs an astronomical (Meeus) Nowruz computation 1986-2099, and vs known official dates. Tehran-midnight boundary and historical Iranian DST are tested. |
| State machine | The Python transition table equals what the real trigger allows/refuses (SQLSTATE 55000), all status pairs. |
| DB error mapping | Each mapped error is produced by a REAL PostgreSQL error (SQLSTATE and constraint name read from psql): 23505 (customer identifiers, product code/name, other), 23503 (incl. cross-organisation = non-existent, same answer), 23514 (amount checks, delivery date), 22003, 55000; unmapped -> 500 without leaking SQL. |
| Seed hashes | The three argon2id hashes written by migration 998 verify with `password.py`. |
| Others | authz matrix (every cell), value rules for all data types and the contract's own example list, refresh policy and grace boundaries, rate limiter, access-token rejections, audit vocabulary, `updated_at` microsecond round trip with PostgreSQL, error table equals the contract's section 15 (parsed from the contract file). |

## 2. NOT verified (do not read this package as proof of these)
* Any FastAPI route, dependency, middleware, `X-Request-Id`, `extra = forbid` schemas, envelopes, pagination.
* `psycopg` itself (the tests use the `psql` CLI), connection handling, transactions-per-request, the retry-once on 40P01/40001.
* Row-lock behaviour of the refresh rotation on PostgreSQL (T-REFRESH): only the *policy function* is tested, with a Python lock.
* Concurrency of submit vs item inserts (T-RACE), in-transaction audit writing (T-AUDIT), tenant isolation through HTTP (T-TENANT), T-E2E.
* `argon2-cffi` (the contract's named library); `password.py` uses `cryptography`'s Argon2id and produces/reads the same PHC strings.
* Repository layer: not written.

## 3. Interpretations I had to make (contract is silent or ambiguous) - please confirm or correct
1. **Quantity/weight failures use `INVALID_MONEY`** (section 15 says "money/quantity format"), including `quantity <= 0`. `bundle_count` uses `VALIDATION_ERROR` (section 10).
2. **Applicability ignores `is_active` of the field**: `applicable_field_ids` = fields of active templates with the product's category; `is_active` is checked next, so `INACTIVE_FIELD` is reachable. (Read literally, D3 "active fields" would make that reason unreachable.)
3. **Digit normalisation is applied to NUMBER, DECIMAL and DATE only**, not to TEXT / SELECT / MULTI_SELECT (it would corrupt free text and option matching).
4. **`SPECIFICATION_INVALID.details` lists every failing element** (one reason each, first failing rule per element), not only the first failing element.
5. **Unknown refresh token**: `INVALID`, but no "revoke all" (no user is known). Expired token: `INVALID` + revoke all (literal reading of section 3.3).
6. **The rate limiter has no reset on success** (the contract counts failures only) and also refuses a correct password while the key is blocked.
7. **Jalali conversion is supported for Gregorian 1900-2099 only**; beyond that, ICU and the 2820-year algorithm diverge (first at 2124-03-20), so the function refuses instead of guessing.
8. **Header totals**: the database defines `subtotal = SUM(ROUND(q*p))`, `discount_total = SUM(discount)`, `tax_total = SUM(tax)`, `grand_total = SUM(line_total)`. `check_header_totals_fit` mirrors this only to refuse overflow early; the Service must still read totals back from the database.

## 4. Requirements for the integration step (these are design obligations, not suggestions)
* **Refresh outcome `REUSE` with `revoke_all_for_user=True` must be COMMITTED although the HTTP request fails.** A handler that raises inside the transaction would roll the revocation back and silently disable the theft response. Commit, then return 401.
* The refresh decision must run while holding `SELECT ... FOR UPDATE` on the token row, inside the same transaction that revokes the old row and inserts the new one.
* Evaluate `now` once per request and pass it to `decide_refresh`; use the database clock consistently with `revoked_at`.
* `numbering.current_series(now)` takes an *aware UTC instant*; call `next_request_number(org, series)` in the same transaction as the header insert. Never derive the series from a stored display date string.
* Every repository method takes `organization_id`; a resource of another organisation is `NOT_FOUND`; a body reference of another organisation is `REFERENCE_NOT_FOUND` (same shape as a non-existent id - tested for the database error path).
* Map database errors only through `errors.map_db_error`; retry once on `is_retryable`, then 503.
* Deployment checklist: exactly one worker (rate limiter is in-process); JWT secret >= 32 bytes from the environment.
* Dependencies to pin in the lock file: PyJWT, argon2-cffi (or keep `cryptography` with Argon2id >= 46), psycopg[binary], FastAPI, httpx (tests).

## 5. Earlier draft found and set aside
While preparing this package I found files in the working folder that I did not write in this pass: an earlier draft of the same core, dated 2026-10-14 00:44-00:50 (`jalali.py`, `dates.py`, `state.py`, `passwords.py`, `ratelimit.py`, `refresh_flow.py`, `concurrency.py` and their tests). They conflict with these modules (different error class and names). They are NOT part of the verified set and are not shipped. One file from it, `tests/astro_nowruz.py`, is used as the independent astronomical reference. `refresh_flow.py` (a transaction-level orchestration with the "commit then raise" note above) is a useful starting point for step 7 but has not been re-verified in this pass.
