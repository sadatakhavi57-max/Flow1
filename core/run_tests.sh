#!/bin/sh
# Usage: ./run_tests.sh <path-to-db/sql> <path-to-SLICE_01_CONTRACT.md>
# Requires PostgreSQL 16 reachable by psql (CREATEs/DROPs tf_core_* databases: TEST SERVER ONLY).
# Exits non-zero if anything fails OR is skipped, so a silent skip cannot pass as success.
cd "$(dirname "$0")" || exit 2
export TF_SQL_DIR="$1" TF_CONTRACT="$2"
out=$(python3 -m unittest discover -s tests -t . 2>&1); rc=$?
echo "$out" | tail -5
case "$out" in *skipped*) echo "SKIPPED TESTS PRESENT - not a full run"; exit 3;; esac
exit $rc
