"""Exercises the REAL runner.py discovery/validation code (psycopg import stubbed; no DB needed)."""
import sys, types
from pathlib import Path
stub = types.ModuleType("psycopg"); stub.Connection = type("Connection", (), {}); stub.Error = type("Error", (Exception,), {})
sys.modules["psycopg"] = stub
sql = Path(sys.argv[1]); sys.path.insert(0, str(sql))
import runner
ms, seeds = runner.discover_files(sql)
fails = []
def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name); cond or fails.append(name)
check("migrations are 001,002,003,004 in order", [m.version for m in ms] == ["001", "002", "003", "004"])
check("seeds are 998,999 in numeric order (998 first)", [m.version for m in seeds] == ["998", "999"])
check("998 is a seed (not recorded as migration)", all(m.version != "998" for m in ms))
check("fresh DB: all four pending in order", [m.version for m in runner.find_pending(ms, {})] == ["001", "002", "003", "004"])
ap = {m.version: (m.name, m.checksum) for m in ms[:2]}
check("001+002 applied: 003 and 004 pending", [m.version for m in runner.find_pending(ms, ap)] == ["003", "004"])
ap3 = {m.version: (m.name, m.checksum) for m in ms[:3]}
check("001-003 applied: only 004 pending", [m.version for m in runner.find_pending(ms, ap3)] == ["004"])
check("004 is named pre_invoices", ms[3].name == "pre_invoices")
try:
    runner.find_pending(ms, {"001": ap["001"], "003": (ms[2].name, ms[2].checksum)}); check("003 applied without 002 is refused", False)
except Exception as e:
    check("003 applied without 002 -> 002 refused (no out-of-order): " + str(e)[:60], True)
try:
    runner.validate_applied_migrations(ms, {**ap, "003": (ms[2].name, "0" * 64)}); check("edited 003 detected by checksum", False)
except RuntimeError as e:
    check("edited 003 detected by checksum", "Checksum mismatch" in str(e))
try:
    runner.validate_applied_migrations(ms, {**ap3, "004": (ms[3].name, "0" * 64)}); check("edited 004 detected by checksum", False)
except RuntimeError as e:
    check("edited 004 detected by checksum", "Checksum mismatch" in str(e))
sys.exit(1 if fails else 0)
