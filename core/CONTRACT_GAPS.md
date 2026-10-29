# Points where the contract is silent and the core made a choice (owner should confirm)

1. quantity <= 0 → 422 VALIDATION_ERROR (format errors → INVALID_MONEY).
2. Login limiter is not reset by a successful login.
3. Logout with the caller's own already-revoked refresh token succeeds (idempotent).
4. Digit normalization is not applied to TEXT / SELECT specification values; only to numbers, dates, identifiers.
5. Malformed specification `field_id` → VALIDATION_ERROR; client-sent extra keys → VALIDATION_ERROR (reason NOT_ALLOWED for server-owned keys, UNKNOWN_FIELD otherwise).
6. Unbounded TEXT columns (address, notes) get an implementation limit of 5000 characters (inputs.TEXT_LIMIT).
7. UUID path/body values: upper-case accepted, canonical lower-case returned; hyphen-less rejected.
8. Quantity/weight accept ASCII or Persian/Arabic digits but NOT the Arabic decimal separator (contract allows it only for DECIMAL specs).
9. Pagination: page >= 1 default 1; page_size 1..200 default 50 (check against the contract section on lists).
10. normalize_identifier depends on the database locale: `[[:space:]]` is ASCII-only under the C locale (verified; mirror matches 1500 random strings), but may also match Unicode spaces (e.g. U+2003) in a UTF-8 locale. Production should state its locale; if it is not C, the Python mirror (used for search only) may differ for such characters.
11. Request numbers: supported series years 1400–1499 only.
12. WORKERS must be 1 (in-process limiter).

## Added with the HTTP layer (stages 1-3) - owner decisions needed
13. A no-op PATCH (nothing really changes) returns the current resource, keeps `updated_at` and writes no audit row (contract T-PATCH allows it).
14. Specification "applicable" = fields of ACTIVE templates of the product's category, whether or not the field itself is active; that is what makes `INACTIVE_FIELD` reachable. Required-at-submit uses only active required fields.
15. Items created inside `POST /purchase-requests` get no separate item CREATE audit row (contract section 13 lists only the header row with `item_count`); items added through `POST .../items` do.
16. `request_date` is returned as a UTC timestamp string; `requested_delivery_date` as `YYYY-MM-DD`.
17. Items are returned in insertion order (`created_at` is set with `clock_timestamp()` so items of one request keep order).
18. Wrong HTTP method keeps status 405 (+ Allow) with code MALFORMED_REQUEST inside the standard envelope (section 15 has no 405 row).
19. `POST /auth/refresh` returns the same shape as login (tokens + user); a user deactivated after rotation gets AUTH_REFRESH_INVALID.
20. The series of a request number is taken from the database `NOW()` of the creating transaction (= `request_date`), not from the application clock.
21. Email, phone, postal_code are validated for type and length only (no business format) - decide if formats are required.
22. Audit rows for customers/products hold the full row (contact data, identifiers): retention and access policy are an owner decision.
23. Contract section 15 says a non-JSON content type is 400 MALFORMED_REQUEST: accepted types are `application/json` and `application/*+json`.

## Added with Stage 4 (pre-invoice) - choices the core made where the owner's order was silent (confirm or change)
24. A replacement may use a different customer than the replaced document: the database and the Service do not compare customers. Decide whether a chain must keep its customer.
25. Dates in the PDF model are Gregorian timestamps/ISO dates; Jalali display is the renderer's job and is not decided.
26. SALES may download a PDF of its own requests' pre-invoices but may NOT generate or retry it (`pre_invoices:pdf` is ADMIN and ACCOUNTING). Decide if SALES should generate.
27. A PDF of a `SUPERSEDED` or `CANCELLED` document can still be generated/downloaded; the document model carries the snapshot only, not the lifecycle status, so such a PDF looks like the issued one (no watermark). Decide how it should look.
28. The "request with an ISSUED pre-invoice cannot be cancelled" rule is a Service rule; migration 002 is frozen, so direct SQL can still cancel such a request. A database guard needs a new migration.
29. A DRAFT pre-invoice does not block cancelling its request; issuing it afterwards fails with `409 STATE_CONFLICT` (`SOURCE_NOT_SUBMITTED`).
30. A document can be replaced once (`uq_pre_invoices_one_successor`); a second DRAFT that points at the same document gets `409 DUPLICATE_RESOURCE` (`ALREADY_REPLACED`) until the first successor DRAFT is cancelled.
31. PDF retry counting: the first attempt of a document is the initial attempt (not a retry, always allowed); retries need >= 60 s after ANY previous attempt and are counted in fixed 15-minute windows that start at the first retry, max 3 per window (so 1 + 3 attempts fit into the first 15 minutes). One definition: `tradeflow_core/pre_invoice.plan_attempt`. The window counters live in `pre_invoice_documents`.
32. PDF library and Persian (RTL) font: NOT decided. The renderer is injected (`create_app(..., pdf_renderer=...)`); the default `UnavailableRenderer` makes every attempt fail with `PDF_RENDERER_UNAVAILABLE`. A library, a pinned version and a font must be approved before production PDF works.
33. The pre-invoice snapshot copies the seller from `organizations` (name, legal name, ids, phone, email, address, postal code). Company-specific printed fields are not built.
34. Audit payloads of pre-invoices are an allowlist (`pre_invoice.AUDIT_KEYS`); the CANCEL reason is stored in `audit_logs.description` (the same place as the request cancel reason).
35. `PDF_FAIL` audit rows are best-effort (written in a savepoint); the failed state of the document row is the source of truth.
