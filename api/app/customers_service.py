"""Customers - contract section 6."""
from __future__ import annotations

from tradeflow_core import customers as cin, products as pin
from tradeflow_core.authz import Cap, authorize
from tradeflow_core.concurrency import check_not_stale
from tradeflow_core import inputs

from . import serialize
from .queries import like_pattern, not_found, page_args, write_audit

_COLS = ", ".join(cin.FIELDS)


class CustomerService:
    def __init__(self, db):
        self.db = db

    def list(self, p, query) -> tuple[list, int, int, int]:
        authorize(p.role_code, Cap.CUSTOMER_READ)
        page, size, offset = page_args(query)
        where, args = ["organization_id = %s"], [p.org_id]
        terms = cin.search_terms(query.get("search"))
        if terms:
            clauses, a = ["name ILIKE %s ESCAPE '\\'"], [like_pattern(terms["text"])]
            if terms["identifier"]:
                for col in ("national_id", "economic_code", "normalize_identifier(mobile)"):     # mobile is stored as typed
                    clauses.append(f"{col} ILIKE %s ESCAPE '\\'")
                    a.append(like_pattern(terms["identifier"]))
            where.append("(" + " OR ".join(clauses) + ")"); args += a
        active = pin.parse_bool_filter(query.get("is_active"))
        if active is not None:
            where.append("is_active = %s"); args.append(active)
        ctype = query.get("customer_type")
        if ctype is not None:
            if ctype not in cin.TYPES:
                raise inputs.verr("customer_type", "MUST_BE_INDIVIDUAL_OR_COMPANY")
            where.append("customer_type = %s"); args.append(ctype)
        w = " AND ".join(where)

        def work(conn):
            total = conn.execute(f"SELECT count(*) AS n FROM customers WHERE {w}", args).fetchone()["n"]
            rows = conn.execute(f"SELECT * FROM customers WHERE {w} ORDER BY name ASC, id ASC LIMIT %s OFFSET %s",
                                args + [size, offset]).fetchall()
            return [serialize.customer(r) for r in rows], total
        items, total = self.db.run(work)
        return items, page, size, total

    def get(self, p, cid: str) -> dict:
        authorize(p.role_code, Cap.CUSTOMER_READ)
        cid = inputs.parse_uuid(cid, "id")

        def work(conn):
            r = conn.execute("SELECT * FROM customers WHERE id = %s AND organization_id = %s", (cid, p.org_id)).fetchone()
            if r is None:
                raise not_found("customer")
            return serialize.customer(r)
        return self.db.run(work)

    def create(self, p, body, ip: str) -> dict:
        authorize(p.role_code, Cap.CUSTOMER_WRITE)
        v = cin.parse_create(body)
        cols = list(cin.FIELDS)

        def work(conn):
            r = conn.execute(f"INSERT INTO customers (organization_id, {', '.join(cols)}) VALUES (%s, {', '.join(['%s'] * len(cols))}) RETURNING *",
                             [p.org_id] + [v[c] for c in cols]).fetchone()
            out = serialize.customer(r)
            write_audit(conn, p, "CREATE", "CUSTOMER", out["id"], new=out, ip=ip)
            return out
        return self.db.run(work)

    def patch(self, p, cid: str, body, ip: str) -> dict:
        authorize(p.role_code, Cap.CUSTOMER_WRITE)
        cid = inputs.parse_uuid(cid, "id")
        changes, client_ts = cin.parse_patch(body)

        def work(conn):
            r = conn.execute("SELECT * FROM customers WHERE id = %s AND organization_id = %s FOR UPDATE", (cid, p.org_id)).fetchone()
            if r is None:
                raise not_found("customer")
            current = serialize.customer(r)
            check_not_stale(client_ts, r["updated_at"], current)           # after the row lock (14.2)
            real = {k: v for k, v in changes.items() if serialize.customer({**r, k: v})[k] != current[k]}
            if not real:
                return current                                              # a no-op PATCH changes nothing and audits nothing
            sets = ", ".join(f"{k} = %s" for k in real)
            new_row = conn.execute(f"UPDATE customers SET {sets} WHERE id = %s AND organization_id = %s RETURNING *",
                                   list(real.values()) + [cid, p.org_id]).fetchone()
            out = serialize.customer(new_row)
            changed = [k for k in real if out[k] != current[k]]
            if not changed:
                return out
            write_audit(conn, p, "UPDATE", "CUSTOMER", cid, old={k: current[k] for k in changed}, new={k: out[k] for k in changed}, ip=ip)
            return out
        return self.db.run(work)
