# Slice 01 – database step (003 + 998)
Files in `sql/`: 001, 002, 999, runner.py are the FROZEN baseline (hashes in `SHA256SUMS` equal `../baseline_sql/SHA256SUMS`); 003 and 998 are new; **004_pre_invoices.sql (Stage 4, v14) is written and NOT yet executed by its author** (applied only by the runner / by the owner after review; it has no seed).
Run the tests (needs psql + a PostgreSQL 16 superuser, python3 with `cryptography`):
    TF_SQL_DIR=$PWD/sql bash tests/test_003_998.sh        # 48 assertions on real PostgreSQL
    python3 -I tests/test_runner_order.py $PWD/sql         # real runner.py logic, 10 checks (expects migrations 001-004 and seeds 998, 999)
Dev login after seeding: organization_code DEMO, username admin|sales|accounting, password in the header of sql/998_dev_seed_auth.sql.
