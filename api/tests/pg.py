"""Tiny psql-based helper for tests that use the REAL PostgreSQL server (no mocks). Tests skip, loudly, when unavailable."""
import os, shutil, subprocess

def available() -> bool:
    if not shutil.which("psql"):
        return False
    r = subprocess.run(["psql", "-X", "-At", "-d", "postgres", "-c", "select 1"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "1"

def psql(db: str, sql: str, *, tuples=True):
    args = ["psql", "-X", "-q", "-d", db, "-v", "ON_ERROR_STOP=1"] + (["-At", "-F", "|"] if tuples else [])
    r = subprocess.run(args, input=sql, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr

def make_db(name: str, sql_dir: str | None = None, files=("001_initial_mvp.sql", "002_harden_mvp.sql",
                                                        "003_org_code_and_username.sql", "004_pre_invoices.sql",
                                                        "998_dev_seed_auth.sql")):
    subprocess.run(["psql", "-X", "-q", "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {name}",
                    "-c", f"CREATE DATABASE {name} ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C'"],
                   check=True, capture_output=True)
    sql_dir = sql_dir or os.environ.get("TF_SQL_DIR")
    for f in files if sql_dir else ():
        r = subprocess.run(["psql", "-X", "-q", "-d", name, "-v", "ON_ERROR_STOP=1", "-1", "-f", os.path.join(sql_dir, f)],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"{f}: {r.stderr}")
