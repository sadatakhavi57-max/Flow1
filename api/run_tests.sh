#!/bin/sh
# Usage: ./run_tests.sh <path-to-db/sql>      (needs PostgreSQL via psql; creates/drops database tf_api_test: TEST SERVER ONLY)
cd "$(dirname "$0")" || exit 2
export TF_SQL_DIR="$1" PYTHONPATH="$PWD:$PWD/../core"
out=$(python3 -m unittest discover -s tests -t . 2>&1); rc=$?
echo "$out" | tail -25
case "$out" in *skipped*) echo "SKIPPED TESTS PRESENT - not a full run"; exit 3;; esac
exit $rc
