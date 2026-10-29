"""Locate and parse tables of SLICE_01_CONTRACT.md so tests can compare code against the document itself."""
import os, re
from pathlib import Path

def contract_path():
    cands = [os.environ.get("TF_CONTRACT"), Path(__file__).resolve().parents[2] / "docs" / "SLICE_01_CONTRACT.md",
             Path(__file__).resolve().parents[2] / "docs_sync" / "SLICE_01_CONTRACT.md"]
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    return None

def section(text: str, heading_prefix: str) -> str:
    m = re.search(rf"^## {re.escape(heading_prefix)}.*?$(.*?)(?=^## )", text, re.S | re.M)
    return m.group(1) if m else ""

def table_rows(block: str):
    rows = []
    for line in block.splitlines():
        if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]            # drop header
