#!/usr/bin/env bash
set -e

# 1. Install PostgreSQL if missing
if ! command -v psql >/dev/null 2>&1; then
    echo "Installing PostgreSQL..."
    sudo apt-get update -qq && sudo apt-get install -y -qq postgresql postgresql-client
fi

# 2. Setup PATH and personal database
export PATH="$(ls -d /usr/lib/postgresql/*/bin | tail -1):$PATH"
export PGDATA="$HOME/pgdata"
export PGSOCK="$HOME/pgsock"
export PGPORT=5433
export PGUSER="$USER"
export PGPASSWORD=""

if [ ! -f "$PGDATA/PG_VERSION" ]; then
    mkdir -p "$PGSOCK"
    initdb -D "$PGDATA" -U "$USER" --auth=trust -E UTF8 --locale=C >/dev/null
fi

if ! pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
    mkdir -p "$PGSOCK"
    pg_ctl -D "$PGDATA" -o "-k $PGSOCK -p $PGPORT -c listen_addresses=''" -l "$HOME/pg.log" -w start
fi

# 3. Setup environment
export PGHOST="$PGSOCK"
export PYTHONPATH="$PWD/api:$PWD/core"
export TF_SQL_DIR="$PWD/db/sql"

# 4. Install ALL Python dependencies (one shot)
echo "Installing dependencies..."
python3 -m pip install -q fastapi uvicorn httpx 'psycopg[binary]' argon2-cffi cryptography PyJWT pytest

# 5. Run tests (db -> core -> api)
echo "Running migration order test..."
python3 -I db/tests/test_runner_order.py "$PWD/db/sql" || { echo "DB test failed"; exit 1; }

echo "Running core tests..."
./core/run_tests.sh "$PWD/db/sql" "$PWD/docs/SLICE_01_CONTRACT.md" || { echo "Core test failed"; exit 1; }

echo "Running api tests..."
./api/run_tests.sh "$PWD/db/sql" || { echo "API test failed"; exit 1; }

echo "ALL TESTS PASSED"
