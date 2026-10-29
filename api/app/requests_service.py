"""Purchase requests, items and pricing - contract sections 8-14. One HTTP request = one transaction (14.1);
every write takes the header lock FIRST (14.2); audit rows are written in the same transaction (13)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from psycopg.types.json import Jsonb

from tradeflow_core import inputs, numbering
from tradeflow_core import products as pin
from tradeflow_core import purchase_inputs as pi
from tradeflow_core.authz import Cap, authorize
from tradeflow_core.concurrency import check_not_stale
from tradeflow_core.errors import AppError, ErrorCode
from tradeflow_core.money import Line, line_total, preview_header_totals
from tradeflow_core.specs import FieldDef, build_snapshot
from tradeflow_core.state import (Status, SubmitItem, assert_editable, assert_product_unchanged, assert_transition,
                                  check_submit)

from . import serialize
from .queries import like_pattern, not_found, page_args, write_audit

_HEADER = ("SELECT r.*, c.name AS customer_name FROM purchase_requests r JOIN customers c ON c.id = r.customer_id"
           " WHERE r.id = %s AND r.organization_id = %s")
_ITEMS = ("SELECT i.*, p.code AS product_code, p.name AS product_name, u.code AS unit_code, u.name AS unit_name,"
          " p.is_active AS product_active, u.is_active AS unit_active, p.category_id AS product_category_id"
          "  FROM purchase_request_items i JOIN products p ON p.id = i.product_id JOIN units u ON u.id = i.unit_id")
_ORDER = " ORDER BY i.created_at ASC, i.id ASC"
_ITEM_PRICES = ("unit_price", "discount_amount", "tax_amount")


def _ref(field: str, code: ErrorCode) -> AppError:
    return AppError(code, details=[{"field": field, "reason": code.value}])


class RequestService:
    def __init__(self, db, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.clock = db, clock

    # ------------------------------------------------------------------ loading helpers
    def _header(self, conn, p, rid, lock=False):
        r = conn.execute(_HEADER + (" FOR UPDATE OF r" if lock else ""), (rid, p.org_id)).fetchone()
        if r is None:
            raise not_found("purchase_request")
        return r

    def _items(self, conn, rid, org_id):
        return conn.execute(_ITEMS + " WHERE i.purchase_request_id = %s AND i.organization_id = %s" + _ORDER, (rid, org_id)).fetchall()

    def _detail(self, conn, p, rid) -> dict:
        d = serialize.request_header(self._header(conn, p, rid))
        d["items"] = [serialize.request_item(i) for i in self._items(conn, rid, p.org_id)]
        return d

    def _authorize_write(self, p, header_row=None):
        """Role first (so a role without the capability never learns anything), ownership once the row is known."""
        if header_row is None:
            authorize(p.role_code, Cap.REQUEST_WRITE, caller_id=p.user_id, owner_id=p.user_id)
        else:
            authorize(p.role_code, Cap.REQUEST_WRITE, caller_id=p.user_id, owner_id=str(header_row["created_by"]))

    def _check_ref(self, conn, table, field, ref_id, org_id):
        r = conn.execute(f"SELECT * FROM {table} WHERE id = %s AND organization_id = %s", (ref_id, org_id)).fetchone()
        if r is None:
            raise _ref(field, ErrorCode.REFERENCE_NOT_FOUND)      # another organization's id and a random id look identical
        if not r["is_active"]:
            raise _ref(field, ErrorCode.INACTIVE_REFERENCE)
        return r

    def _spec_context(self, conn, org_id, category_id):
        """All fields of the organization + ids applicable to a category (fields of ACTIVE templates of that category;
        an inactive field stays 'applicable' so that INACTIVE_FIELD is reachable) + ids of required active ones."""
        rows = conn.execute("""SELECT f.id, f.code, f.name, f.data_type, f.is_active, f.is_required, f.options,
                                      t.category_id AS cat, t.is_active AS template_active
                                 FROM product_specification_fields f JOIN product_specification_templates t ON t.id = f.template_id
                                WHERE f.organization_id = %s""", (org_id,)).fetchall()
        fields, applicable, required = {}, [], []
        for r in rows:
            fid = str(r["id"])
            opts = tuple(r["options"]) if r["options"] else None
            fields[fid] = FieldDef(fid, r["code"], r["name"], r["data_type"], r["is_active"], r["is_required"], opts)
            if r["template_active"] and r["cat"] is not None and str(r["cat"]) == str(category_id):
                applicable.append(fid)
                if r["is_active"] and r["is_required"]:
                    required.append(fid)
        return fields, applicable, required

    def _prepare_item(self, conn, p, inp: dict, prefix: str, existing=None) -> dict:
        """Validated, fully computed column values for one item (create when `existing` is None, else a merged patch)."""
        if existing is None:
            product = self._check_ref(conn, "products", f"{prefix}product_id", inp["product_id"], p.org_id)
            unit_id = inp.get("unit_id") or str(product["default_unit_id"])
        else:
            product = conn.execute("SELECT * FROM products WHERE id = %s", (existing["product_id"],)).fetchone()
            unit_id = inp.get("unit_id") or str(existing["unit_id"])
        if existing is None or "unit_id" in inp:
            self._check_ref(conn, "units", f"{prefix}unit_id", unit_id, p.org_id)
        base = existing or {}
        merged = {k: inp[k] if k in inp else base.get(k) for k in
                  ("quantity", "bundle_count", "estimated_weight", "notes") + _ITEM_PRICES}
        merged["unit_id"] = unit_id
        merged["product_id"] = str(product["id"])
        merged["line_total"] = line_total(Decimal(merged["quantity"]), Decimal(merged["unit_price"]),
                                          Decimal(merged["discount_amount"]), Decimal(merged["tax_amount"]))
        if "specifications" in inp:
            fields, applicable, _ = self._spec_context(conn, p.org_id, product["category_id"])
            merged["specifications"] = build_snapshot(inp["specifications"], fields, applicable)
        else:
            merged["specifications"] = base.get("specifications", [])
        return merged

    @staticmethod
    def _precheck_totals(rows, replace_id=None, extra=None):
        """Section 10 range pre-check of the header totals over (existing items - replaced one + new values)."""
        lines = [Line(Decimal(r["quantity"]), Decimal(r["unit_price"]), Decimal(r["discount_amount"]), Decimal(r["tax_amount"]))
                 for r in rows if str(r["id"]) != replace_id]
        lines += [Line(Decimal(e["quantity"]), Decimal(e["unit_price"]), Decimal(e["discount_amount"]), Decimal(e["tax_amount"])) for e in (extra or [])]
        preview_header_totals(lines)

    def _insert_item(self, conn, p, rid, m: dict):
        return conn.execute(
            "INSERT INTO purchase_request_items (organization_id, purchase_request_id, product_id, quantity, unit_id, bundle_count,"
            " estimated_weight, unit_price, discount_amount, tax_amount, line_total, notes, specifications, created_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, clock_timestamp()) RETURNING id",
            (p.org_id, rid, m["product_id"], m["quantity"], m["unit_id"], m["bundle_count"], m["estimated_weight"],
             m["unit_price"], m["discount_amount"], m["tax_amount"], m["line_total"], m["notes"], Jsonb(m["specifications"]))).fetchone()["id"]

    def _item_row(self, conn, p, item_id):
        return conn.execute(_ITEMS + " WHERE i.id = %s AND i.organization_id = %s", (item_id, p.org_id)).fetchone()

    # ------------------------------------------------------------------ create
    def create(self, p, body, ip: str) -> dict:
        authorize(p.role_code, Cap.REQUEST_CREATE)
        v = pi.parse_request_create(body, numbering.tehran_today(self.clock()))

        def work(conn):
            self._check_ref(conn, "customers", "customer_id", v["customer_id"], p.org_id)
            prepared = [self._prepare_item(conn, p, it, f"items[{i}].") for i, it in enumerate(v["items"])]
            self._precheck_totals([], extra=prepared)
            now = conn.execute("SELECT NOW() AS t").fetchone()["t"]               # the creation instant = request_date (same transaction)
            series = numbering.series_for(now)
            n = conn.execute("SELECT next_request_number(%s, %s) AS n", (p.org_id, series)).fetchone()["n"]
            rid = conn.execute(
                "INSERT INTO purchase_requests (organization_id, request_number, customer_id, requested_delivery_date, notes, created_by, updated_by)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (p.org_id, numbering.format_request_number(series, n), v["customer_id"], v["requested_delivery_date"], v["notes"],
                 p.user_id, p.user_id)).fetchone()["id"]
            for m in prepared:
                self._insert_item(conn, p, rid, m)
            out = self._detail(conn, p, str(rid))
            head = {k: val for k, val in out.items() if k != "items"}
            write_audit(conn, p, "CREATE", "PURCHASE_REQUEST", str(rid), new={**head, "item_count": len(out["items"])}, ip=ip)
            return out
        return self.db.run(work)

    # ------------------------------------------------------------------ read
    def list(self, p, query):
        authorize(p.role_code, Cap.REQUEST_READ)
        page, size, offset = page_args(query)
        where, args = ["r.organization_id = %s"], [p.org_id]
        st = query.get("status")
        if st is not None:
            if st not in {s.value for s in Status}:
                raise inputs.verr("status", "UNKNOWN_STATUS")
            where.append("r.status = %s"); args.append(st)
        if query.get("customer_id") is not None:
            where.append("r.customer_id = %s"); args.append(inputs.parse_uuid(query["customer_id"], "customer_id"))
        cf, ct = pi.parse_date_param(query.get("created_from"), "created_from"), pi.parse_date_param(query.get("created_to"), "created_to")
        if cf:
            where.append("r.created_at >= (%s::date::timestamp AT TIME ZONE 'Asia/Tehran')"); args.append(cf)
        if ct:
            where.append("r.created_at < ((%s::date + 1)::timestamp AT TIME ZONE 'Asia/Tehran')"); args.append(ct)
        term = inputs.text(query.get("search"), "search", 100)
        if term:
            where.append("(r.request_number ILIKE %s ESCAPE '\\' OR c.name ILIKE %s ESCAPE '\\')")
            args += [like_pattern(term)] * 2
        w = " AND ".join(where)

        def work(conn):
            base = "FROM purchase_requests r JOIN customers c ON c.id = r.customer_id WHERE " + w
            total = conn.execute("SELECT count(*) AS n " + base, args).fetchone()["n"]
            rows = conn.execute("SELECT r.*, c.name AS customer_name, (SELECT count(*) FROM purchase_request_items i WHERE i.purchase_request_id = r.id) AS item_count "
                                + base + " ORDER BY r.created_at DESC, r.id DESC LIMIT %s OFFSET %s", args + [size, offset]).fetchall()
            return [serialize.request_header(r) for r in rows], total
        items, total = self.db.run(work)
        return items, page, size, total

    def get(self, p, rid: str) -> dict:
        authorize(p.role_code, Cap.REQUEST_READ)
        rid = inputs.parse_uuid(rid, "id")
        return self.db.run(lambda conn: self._detail(conn, p, rid))

    # ------------------------------------------------------------------ header patch / submit / cancel
    def patch(self, p, rid: str, body, ip: str) -> dict:
        self._authorize_write(p)
        rid = inputs.parse_uuid(rid, "id")
        changes, client_ts = pi.parse_request_patch(body, numbering.tehran_today(self.clock()))

        def work(conn):
            r = self._header(conn, p, rid, lock=True)
            self._authorize_write(p, r)
            assert_editable(r["status"])
            current = serialize.request_header(r)
            check_not_stale(client_ts, r["updated_at"], {**current, "items": [serialize.request_item(i) for i in self._items(conn, rid, p.org_id)]})
            flat = {"customer_id": current["customer"]["id"], "requested_delivery_date": current["requested_delivery_date"], "notes": current["notes"]}
            wire = {k: (v.isoformat() if k == "requested_delivery_date" and v is not None else v) for k, v in changes.items()}
            real = {k: v for k, v in wire.items() if flat[k] != v}
            if not real:
                return self._detail(conn, p, rid)
            if "customer_id" in real:
                self._check_ref(conn, "customers", "customer_id", real["customer_id"], p.org_id)
            conn.execute(f"UPDATE purchase_requests SET {', '.join(f'{k} = %s' for k in real)}, updated_by = %s WHERE id = %s AND organization_id = %s",
                         list(real.values()) + [p.user_id, rid, p.org_id])
            out = self._detail(conn, p, rid)
            new_flat = {"customer_id": out["customer"]["id"], "requested_delivery_date": out["requested_delivery_date"], "notes": out["notes"]}
            write_audit(conn, p, "UPDATE", "PURCHASE_REQUEST", rid, old={k: flat[k] for k in real}, new={k: new_flat[k] for k in real}, ip=ip)
            return out
        return self.db.run(work)

    def submit(self, p, rid: str, ip: str) -> dict:
        self._authorize_write(p)
        rid = inputs.parse_uuid(rid, "id")

        def work(conn):
            r = self._header(conn, p, rid, lock=True)
            self._authorize_write(p, r)
            customer = conn.execute("SELECT is_active FROM customers WHERE id = %s", (r["customer_id"],)).fetchone()
            rows = self._items(conn, rid, p.org_id)
            required_by_cat = {}
            items = []
            for i in rows:
                cat = str(i["product_category_id"])
                if cat not in required_by_cat:
                    required_by_cat[cat] = tuple(self._spec_context(conn, p.org_id, cat)[2])
                items.append(SubmitItem(str(i["id"]), i["product_active"], i["unit_active"], Decimal(i["unit_price"]),
                                        i["specifications"], required_by_cat[cat]))
            check_submit(r["status"], customer["is_active"], items)
            assert_transition(r["status"], Status.SUBMITTED.value)
            conn.execute("UPDATE purchase_requests SET status = 'SUBMITTED', updated_by = %s WHERE id = %s AND organization_id = %s", (p.user_id, rid, p.org_id))
            out = self._detail(conn, p, rid)
            write_audit(conn, p, "SUBMIT", "PURCHASE_REQUEST", rid, old={"status": "DRAFT"},
                        new={"status": "SUBMITTED", "grand_total": out["grand_total"]}, ip=ip)
            return out
        return self.db.run(work)

    def cancel(self, p, rid: str, body, ip: str) -> dict:
        self._authorize_write(p)
        rid = inputs.parse_uuid(rid, "id")
        reason = pi.parse_cancel(body)

        def work(conn):
            r = self._header(conn, p, rid, lock=True)
            self._authorize_write(p, r)
            assert_transition(r["status"], Status.CANCELLED.value)
            # Stage 4 (contract section 26): a request with an ISSUED pre-invoice is not cancelled through this route.
            # The header lock is held, and issuing takes the same lock first, so the check cannot race with an issue.
            active = conn.execute("SELECT id FROM pre_invoices WHERE organization_id = %s AND source_request_id = %s AND status = 'ISSUED'",
                                  (p.org_id, rid)).fetchone()
            if active is not None:
                raise AppError(ErrorCode.STATE_CONFLICT, details={"reason": "ACTIVE_PRE_INVOICE", "pre_invoice_id": str(active["id"])})
            conn.execute("UPDATE purchase_requests SET status = 'CANCELLED', updated_by = %s WHERE id = %s AND organization_id = %s", (p.user_id, rid, p.org_id))
            write_audit(conn, p, "CANCEL", "PURCHASE_REQUEST", rid, old={"status": r["status"]}, new={"status": "CANCELLED"}, description=reason, ip=ip)
            return self._detail(conn, p, rid)
        return self.db.run(work)

    # ------------------------------------------------------------------ items
    def add_item(self, p, rid: str, body, ip: str) -> dict:
        self._authorize_write(p)
        rid = inputs.parse_uuid(rid, "id")
        inp = pi.parse_item_create(body)

        def work(conn):
            r = self._header(conn, p, rid, lock=True)
            self._authorize_write(p, r)
            assert_editable(r["status"])
            m = self._prepare_item(conn, p, inp, "")
            self._precheck_totals(self._items(conn, rid, p.org_id), extra=[m])
            item_id = str(self._insert_item(conn, p, rid, m))
            item = serialize.request_item(self._item_row(conn, p, item_id))
            write_audit(conn, p, "CREATE", "PURCHASE_REQUEST_ITEM", item_id, new=item, ip=ip)
            return {"item": item, "request": serialize.request_header(self._header(conn, p, rid))}
        return self.db.run(work)

    def _locked_item(self, conn, p, item_id):
        """Lock order 14.2: find the parent, lock the HEADER first, then re-read the item (it may have been deleted meanwhile)."""
        pre = conn.execute("SELECT purchase_request_id FROM purchase_request_items WHERE id = %s AND organization_id = %s", (item_id, p.org_id)).fetchone()
        if pre is None:
            raise not_found("purchase_request_item")
        rid = str(pre["purchase_request_id"])
        header = self._header(conn, p, rid, lock=True)
        item = self._item_row(conn, p, item_id)
        if item is None:
            raise not_found("purchase_request_item")
        return rid, header, item

    def patch_item(self, p, item_id: str, body, ip: str) -> dict:
        self._authorize_write(p)
        item_id = inputs.parse_uuid(item_id, "id")
        inp, client_ts = pi.parse_item_patch(body)

        def work(conn):
            rid, header, item = self._locked_item(conn, p, item_id)
            self._authorize_write(p, header)
            assert_editable(header["status"])
            current = serialize.request_item(item)
            check_not_stale(client_ts, item["updated_at"], current)
            assert_product_unchanged(str(item["product_id"]), inp)
            inp2 = {k: v for k, v in inp.items() if k != "product_id"}
            m = self._prepare_item(conn, p, inp2, "", existing=dict(item))
            changed = {}
            probe = {**item, **{k: m[k] for k in ("quantity", "unit_id", "bundle_count", "estimated_weight", "unit_price", "discount_amount",
                                                   "tax_amount", "line_total", "notes", "specifications")}}
            probe_json = serialize.request_item(probe)
            for k in ("quantity", "bundle_count", "estimated_weight", "unit_price", "discount_amount", "tax_amount", "line_total", "notes", "specifications"):
                if probe_json[k] != current[k]:
                    changed[k] = k
            if str(m["unit_id"]) != str(item["unit_id"]):
                changed["unit_id"] = "unit_id"
            if not changed:
                return {"item": current, "request": serialize.request_header(header)}
            self._precheck_totals(self._items(conn, rid, p.org_id), replace_id=item_id, extra=[m])
            conn.execute("UPDATE purchase_request_items SET quantity=%s, unit_id=%s, bundle_count=%s, estimated_weight=%s, unit_price=%s,"
                         " discount_amount=%s, tax_amount=%s, line_total=%s, notes=%s, specifications=%s WHERE id=%s AND organization_id=%s",
                         (m["quantity"], m["unit_id"], m["bundle_count"], m["estimated_weight"], m["unit_price"], m["discount_amount"],
                          m["tax_amount"], m["line_total"], m["notes"], Jsonb(m["specifications"]), item_id, p.org_id))
            new_item = serialize.request_item(self._item_row(conn, p, item_id))
            old_d = {k: (current["unit"]["id"] if k == "unit_id" else current[k]) for k in changed}
            new_d = {k: (new_item["unit"]["id"] if k == "unit_id" else new_item[k]) for k in changed}
            write_audit(conn, p, "UPDATE", "PURCHASE_REQUEST_ITEM", item_id, old=old_d, new=new_d, ip=ip)
            return {"item": new_item, "request": serialize.request_header(self._header(conn, p, rid))}
        return self.db.run(work)

    def delete_item(self, p, item_id: str, ip: str) -> dict:
        self._authorize_write(p)
        item_id = inputs.parse_uuid(item_id, "id")

        def work(conn):
            rid, header, item = self._locked_item(conn, p, item_id)
            self._authorize_write(p, header)
            assert_editable(header["status"])
            old = serialize.request_item(item)
            conn.execute("DELETE FROM purchase_request_items WHERE id = %s AND organization_id = %s", (item_id, p.org_id))
            write_audit(conn, p, "DELETE", "PURCHASE_REQUEST_ITEM", item_id, old=old, ip=ip)
            return {"request": serialize.request_header(self._header(conn, p, rid))}
        return self.db.run(work)

    # ------------------------------------------------------------------ pricing
    def _pricing_view(self, conn, p, rid) -> dict:
        h = serialize.request_header(self._header(conn, p, rid))
        lines = [{"item_id": i["id"], "product": i["product"], "quantity": i["quantity"], "unit_price": i["unit_price"],
                  "discount_amount": i["discount_amount"], "tax_amount": i["tax_amount"], "line_total": i["line_total"]}
                 for i in (serialize.request_item(r) for r in self._items(conn, rid, p.org_id))]
        return {"request_id": rid, "status": h["status"], "currency_unit": "RIAL", "lines": lines, "subtotal": h["subtotal"],
                "discount_total": h["discount_total"], "tax_total": h["tax_total"], "grand_total": h["grand_total"], "updated_at": h["updated_at"]}

    def get_pricing(self, p, rid: str) -> dict:
        authorize(p.role_code, Cap.REQUEST_READ)
        rid = inputs.parse_uuid(rid, "id")
        return self.db.run(lambda conn: self._pricing_view(conn, p, rid))

    def set_pricing(self, p, rid: str, body, ip: str) -> dict:
        self._authorize_write(p)
        rid = inputs.parse_uuid(rid, "id")
        lines, client_ts = pi.parse_pricing(body)

        def work(conn):
            r = self._header(conn, p, rid, lock=True)
            self._authorize_write(p, r)
            assert_editable(r["status"])
            current_view = self._pricing_view(conn, p, rid)
            check_not_stale(client_ts, r["updated_at"], current_view)
            rows = {str(i["id"]): i for i in self._items(conn, rid, p.org_id)}
            updates = []
            for idx, ln in enumerate(lines):
                row = rows.get(ln["item_id"])
                if row is None:                                    # other request / other organization / unknown: one identical answer
                    raise _ref(f"lines[{idx}].item_id", ErrorCode.REFERENCE_NOT_FOUND)
                new = {k: ln.get(k, row[k]) for k in _ITEM_PRICES}
                lt = line_total(Decimal(row["quantity"]), Decimal(new["unit_price"]), Decimal(new["discount_amount"]), Decimal(new["tax_amount"]))
                if any(Decimal(new[k]) != Decimal(row[k]) for k in _ITEM_PRICES):
                    updates.append((row, new, lt))
            if not updates:
                return current_view
            replaced = {str(row["id"]): {**row, **new} for row, new, _ in updates}
            all_lines = [Line(Decimal(x["quantity"]), Decimal(x["unit_price"]), Decimal(x["discount_amount"]), Decimal(x["tax_amount"]))
                         for x in (replaced.get(k, rows[k]) for k in rows)]
            preview_header_totals(all_lines)
            for row, new, lt in updates:
                conn.execute("UPDATE purchase_request_items SET unit_price=%s, discount_amount=%s, tax_amount=%s, line_total=%s WHERE id=%s AND organization_id=%s",
                             (new["unit_price"], new["discount_amount"], new["tax_amount"], lt, row["id"], p.org_id))
                old_d = {k: serialize._money(row[k]) for k in _ITEM_PRICES if Decimal(new[k]) != Decimal(row[k])}
                new_d = {k: serialize._money(new[k]) for k in old_d}
                write_audit(conn, p, "UPDATE", "PURCHASE_REQUEST_ITEM", str(row["id"]), old=old_d, new=new_d, ip=ip)
            conn.execute("UPDATE purchase_requests SET updated_by = %s WHERE id = %s AND organization_id = %s", (p.user_id, rid, p.org_id))
            return self._pricing_view(conn, p, rid)
        return self.db.run(work)
