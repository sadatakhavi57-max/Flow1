"""GET /audit-logs (ADMIN only, read-only) - contract section 13."""
from __future__ import annotations

from tradeflow_core import audit, inputs
from tradeflow_core import purchase_inputs as pi
from tradeflow_core.authz import Cap, authorize

from . import serialize
from .queries import page_args


class AuditService:
    def __init__(self, db):
        self.db = db

    def list(self, p, query):
        authorize(p.role_code, Cap.AUDIT_READ)
        page, size, offset = page_args(query)
        where, args = ["organization_id = %s"], [p.org_id]
        et, ac = query.get("entity_type"), query.get("action")
        if et is not None:
            if et not in {e.value for e in audit.AuditEntity}:
                raise inputs.verr("entity_type", "UNKNOWN_ENTITY_TYPE")
            where.append("entity_type = %s"); args.append(et)
        if ac is not None:
            if ac not in {a.value for a in audit.AuditAction}:
                raise inputs.verr("action", "UNKNOWN_ACTION")
            where.append("action = %s"); args.append(ac)
        for param, col in (("entity_id", "entity_id"), ("actor_id", "user_id")):
            if query.get(param) is not None:
                where.append(f"{col} = %s"); args.append(inputs.parse_uuid(query[param], param))
        cf, ct = pi.parse_date_param(query.get("created_from"), "created_from"), pi.parse_date_param(query.get("created_to"), "created_to")
        if cf:
            where.append("created_at >= (%s::date::timestamp AT TIME ZONE 'Asia/Tehran')"); args.append(cf)
        if ct:
            where.append("created_at < ((%s::date + 1)::timestamp AT TIME ZONE 'Asia/Tehran')"); args.append(ct)
        w = " AND ".join(where)

        def work(conn):
            total = conn.execute(f"SELECT count(*) AS n FROM audit_logs WHERE {w}", args).fetchone()["n"]
            rows = conn.execute(f"SELECT * FROM audit_logs WHERE {w} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s", args + [size, offset]).fetchall()
            return [serialize.audit_row(r) for r in rows], total
        items, total = self.db.run(work)
        return items, page, size, total
