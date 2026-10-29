"""Real-PostgreSQL helpers (psql CLI). Tests that need them are SKIPPED, loudly, when psql or the SQL folder is absent."""
import os, shutil, subprocess, unittest

SQL_DIR = os.environ.get("TF_SQL_DIR")


def available() -> bool:
    if not (shutil.which("psql") and SQL_DIR and os.path.isdir(SQL_DIR)):
        return False
    return subprocess.run(["psql", "-X", "-At", "-d", "postgres", "-c", "select 1"], capture_output=True).returncode == 0


def requires_pg(cls):
    return unittest.skipUnless(available(), "SKIPPED: needs psql + a reachable PostgreSQL 16 + TF_SQL_DIR (not run here)")(cls)


def psql(db, sql=None, file=None, tuples=True):
    cmd = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db] + (["-At", "-F", "|"] if tuples else [])
    if sql is not None and len(sql) > 50000:                       # avoid "argument list too long"
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
            f.write(sql)
        file, sql = f.name, None
    cmd += ["-c", sql] if sql is not None else ["-f", file]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout


def fresh_db(name, seeds=True):
    psql("postgres", f"DROP DATABASE IF EXISTS {name}")
    psql("postgres", f"CREATE DATABASE {name} ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C'")
    files = ["001_initial_mvp.sql", "002_harden_mvp.sql", "003_org_code_and_username.sql"] + (["998_dev_seed_auth.sql"] if seeds else [])
    for f in files:
        subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", name, "-1", "-f", os.path.join(SQL_DIR, f)],
                       check=True, capture_output=True)
    return name


class PsqlSession:
    """A persistent psql process = one real database session, so a test can interleave Python logic between statements
    of ONE transaction (needed to exercise SELECT ... FOR UPDATE races)."""
    END = "__tf_end__"

    def __init__(self, db):
        self.p = subprocess.Popen(["psql", "-X", "-q", "-At", "-F", "|", "-d", db], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def query(self, sql):
        self.p.stdin.write(sql.rstrip().rstrip(";") + ";\n\\echo " + self.END + "\n")
        self.p.stdin.flush()
        out = []
        while True:
            line = self.p.stdout.readline()
            if line == "":
                raise RuntimeError("psql session died: " + "\n".join(out))
            line = line.rstrip("\n")
            if line == self.END:
                break
            out.append(line)
        for l in out:
            if l.startswith("ERROR:"):
                raise RuntimeError("; ".join(out))
        return [l for l in out if l]

    def close(self):
        try:
            self.p.stdin.write("\\q\n"); self.p.stdin.flush()
        except Exception:
            pass
        self.p.wait(timeout=10)
