"""Products, specifications, lookups and the organization - contract sections 5 and 7 (ADR-063)."""
from __future__ import annotations

from tradeflow_core import inputs, products as pin
from tradeflow_core.authz import Cap, authorize
from tradeflow_core.concurrency import check_not_stale
from tradeflow_core.errors import AppError, ErrorCode

from . import serialize
from .queries import like_pattern, not_found, page_args, write_audit

_PRODUCT_SQL = """
SELECT p.*, c.code AS category_code, c.name AS category_name, u.code AS unit_code, u.name AS unit_name, u.unit_type
  FROM products p
  JOIN product_categories c ON c.id = p.category_id
  JOIN units u ON u.id = p.default_unit_id
"""


def _ref_error(field: str, code: ErrorCode) -> AppError:
    return AppError(code, details=[{"field": field, "reason": code.value}])


def _check_reference(conn, table: str, field: str, ref_id: str, org_id: str):
    """Exists in this organization AND active. Another organization's id and a random id give the SAME response (T-TENANT b)."""
    r = conn.execute(f"SELECT is_active FROM {table} WHERE id = %s AND organization_id = %s", (ref_id, org_id)).fetchone()
    if r is None:
        raise _ref_error(field, ErrorCode.REFERENCE_NOT_FOUND)
    if not r["is_active"]:
        raise _ref_error(field, ErrorCode.INACTIVE_REFERENCE)


class ProductService:
    def __init__(self, db):
        self.db = db

    # ----------------------------------------------------------------- products
    def list(self, p, query):
        authorize(p.role_code, Cap.PRODUCT_READ)
        page, size, offset = page_args(query)
        where, args = ["p.organization_id = %s"], [p.org_id]
        term = inputs.text(query.get("search"), "search", 100)
        if term:
            where.append("(p.name ILIKE %s ESCAPE '\\' OR p.code ILIKE %s ESCAPE '\\')")
            args += [like_pattern(term)] * 2
        if query.get("category_id") is not None:
            where.append("p.category_id = %s"); args.append(inputs.parse_uuid(query["category_id"], "category_id"))
        active = pin.parse_bool_filter(query.get("is_active"))
        if active is not None:
            where.append("p.is_active = %s"); args.append(active)
        w = " AND ".join(where)

        def work(conn):
            total = conn.execute(f"SELECT count(*) AS n FROM products p WHERE {w}", args).fetchone()["n"]
            rows = conn.execute(f"{_PRODUCT_SQL} WHERE {w} ORDER BY p.name ASC, p.id ASC LIMIT %s OFFSET %s", args + [size, offset]).fetchall()
            return [serialize.product(r) for r in rows], total
        items, total = self.db.run(work)
        return items, page, size, total

    def _load(self, conn, org_id, pid, lock=False):
        r = conn.execute(f"{_PRODUCT_SQL} WHERE p.id = %s AND p.organization_id = %s" + (" FOR UPDATE OF p" if lock else ""),
                         (pid, org_id)).fetchone()
        if r is None:
            raise not_found("product")
        return r

    def get(self, p, pid: str) -> dict:
        authorize(p.role_code, Cap.PRODUCT_READ)
        pid = inputs.parse_uuid(pid, "id")
        return self.db.run(lambda conn: serialize.product(self._load(conn, p.org_id, pid)))

    def create(self, p, body, ip: str) -> dict:
        authorize(p.role_code, Cap.PRODUCT_WRITE)
        v = pin.parse_create(body)

        def work(conn):
            _check_reference(conn, "product_categories", "category_id", v["category_id"], p.org_id)
            _check_reference(conn, "units", "default_unit_id", v["default_unit_id"], p.org_id)
            new_id = conn.execute(
                "INSERT INTO products (organization_id, code, name, description, category_id, default_unit_id, is_active)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (p.org_id, v["code"], v["name"], v["description"], v["category_id"], v["default_unit_id"], v["is_active"])).fetchone()["id"]
            out = serialize.product(self._load(conn, p.org_id, new_id))
            write_audit(conn, p, "CREATE", "PRODUCT", out["id"], new=out, ip=ip)
            return out
        return self.db.run(work)

    def patch(self, p, pid: str, body, ip: str) -> dict:
        authorize(p.role_code, Cap.PRODUCT_WRITE)
        pid = inputs.parse_uuid(pid, "id")
        changes, client_ts = pin.parse_patch(body)

        def work(conn):
            r = self._load(conn, p.org_id, pid, lock=True)
            current = serialize.product(r)
            check_not_stale(client_ts, r["updated_at"], current)
            flat = {"code": current["code"], "name": current["name"], "description": current["description"],
                    "category_id": current["category"]["id"], "default_unit_id": current["default_unit"]["id"],
                    "is_active": current["is_active"]}
            real = {k: v for k, v in changes.items() if flat[k] != v}
            if not real:
                return current
            for fld, table in (("category_id", "product_categories"), ("default_unit_id", "units")):
                if fld in real:
                    _check_reference(conn, table, fld, real[fld], p.org_id)
            conn.execute(f"UPDATE products SET {', '.join(f'{k} = %s' for k in real)} WHERE id = %s AND organization_id = %s",
                         list(real.values()) + [pid, p.org_id])
            out = serialize.product(self._load(conn, p.org_id, pid))
            new_flat = {"code": out["code"], "name": out["name"], "description": out["description"],
                        "category_id": out["category"]["id"], "default_unit_id": out["default_unit"]["id"], "is_active": out["is_active"]}
            write_audit(conn, p, "UPDATE", "PRODUCT", pid, old={k: flat[k] for k in real}, new={k: new_flat[k] for k in real}, ip=ip)
            return out
        return self.db.run(work)

    # ----------------------------------------------------------------- specifications
    def specifications(self, p, pid: str) -> dict:
        authorize(p.role_code, Cap.PRODUCT_READ)
        pid = inputs.parse_uuid(pid, "id")

        def work(conn):
            prod = conn.execute("SELECT category_id FROM products WHERE id = %s AND organization_id = %s", (pid, p.org_id)).fetchone()
            if prod is None:
                raise not_found("product")
            rows = conn.execute("""
                SELECT f.id AS field_id, f.code, f.name, f.data_type, f.is_required, f.display_order, f.options,
                       v.value_text, v.value_number, v.value_decimal, v.value_boolean, v.value_date, v.value_option, v.value_options
                  FROM product_specification_fields f
                  JOIN product_specification_templates t ON t.id = f.template_id
                  LEFT JOIN product_specification_values v ON v.field_id = f.id AND v.product_id = %s
                 WHERE f.organization_id = %s AND t.organization_id = %s AND t.category_id = %s
                   AND f.is_active AND t.is_active
                 ORDER BY f.display_order ASC, f.code ASC""", (pid, p.org_id, p.org_id, prod["category_id"])).fetchall()
            fields = [{"field_id": str(r["field_id"]), "code": r["code"], "name": r["name"], "data_type": r["data_type"],
                       "is_required": r["is_required"], "display_order": r["display_order"], "options": r["options"],
                       "value": serialize.spec_value(r)} for r in rows]
            return {"product_id": pid, "fields": fields}
        return self.db.run(work)

    # ----------------------------------------------------------------- lookups (ADR-063) and organization
    def categories(self, p, query):
        authorize(p.role_code, Cap.LOOKUP_READ)
        page, size, offset = page_args(query)
        active = pin.parse_bool_filter(query.get("is_active"))
        active = True if active is None and "is_active" not in query else active        # default filter: active only
        where, args = ["organization_id = %s"], [p.org_id]
        if active is not None:
            where.append("is_active = %s"); args.append(active)
        term = inputs.text(query.get("search"), "search", 100)
        if term:
            where.append("name ILIKE %s ESCAPE '\\'"); args.append(like_pattern(term))
        w = " AND ".join(where)

        def work(conn):
            total = conn.execute(f"SELECT count(*) AS n FROM product_categories WHERE {w}", args).fetchone()["n"]
            rows = conn.execute(f"SELECT * FROM product_categories WHERE {w} ORDER BY name ASC, id ASC LIMIT %s OFFSET %s", args + [size, offset]).fetchall()
            return [serialize.category(r) for r in rows], total
        items, total = self.db.run(work)
        return items, page, size, total

    def units(self, p, query):
        authorize(p.role_code, Cap.LOOKUP_READ)
        page, size, offset = page_args(query)
        active = pin.parse_bool_filter(query.get("is_active"))
        active = True if active is None and "is_active" not in query else active
        where, args = ["organization_id = %s"], [p.org_id]
        if active is not None:
            where.append("is_active = %s"); args.append(active)
        utype = pin.parse_unit_type_filter(query.get("unit_type"))
        if utype:
            where.append("unit_type = %s"); args.append(utype)
        w = " AND ".join(where)

        def work(conn):
            total = conn.execute(f"SELECT count(*) AS n FROM units WHERE {w}", args).fetchone()["n"]
            rows = conn.execute(f"SELECT * FROM units WHERE {w} ORDER BY code ASC, id ASC LIMIT %s OFFSET %s", args + [size, offset]).fetchall()
            return [serialize.unit(r) for r in rows], total
        items, total = self.db.run(work)
        return items, page, size, total

    def organization(self, p, oid: str | None = None):
        authorize(p.role_code, Cap.ORG_READ)
        if oid is not None:
            oid = inputs.parse_uuid(oid, "id")
            if oid != p.org_id:
                raise not_found("organization")

        def work(conn):
            r = conn.execute("SELECT * FROM organizations WHERE id = %s", (p.org_id,)).fetchone()
            if r is None:
                raise not_found("organization")
            return serialize.organization(r)
        return self.db.run(work)
