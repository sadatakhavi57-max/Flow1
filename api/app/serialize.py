"""Row -> API JSON. Ids are strings, timestamps use the contract format, numeric(20,0) is an integer string."""
from __future__ import annotations

from decimal import Decimal

from tradeflow_core.concurrency import format_ts


def _s(v):
    return None if v is None else str(v)


def customer(r) -> dict:
    return {"id": _s(r["id"]), "customer_type": r["customer_type"], "name": r["name"], "national_id": r["national_id"],
            "economic_code": r["economic_code"], "registration_number": r["registration_number"], "mobile": r["mobile"],
            "phone": r["phone"], "email": r["email"], "address": r["address"], "postal_code": r["postal_code"],
            "credit_limit": str(Decimal(r["credit_limit"]).quantize(Decimal(1))), "is_active": r["is_active"],
            "created_at": format_ts(r["created_at"]), "updated_at": format_ts(r["updated_at"])}


def organization(r) -> dict:
    return {"id": _s(r["id"]), "code": r["code"], "name": r["name"], "legal_name": r["legal_name"],
            "national_id": r["national_id"], "economic_code": r["economic_code"],
            "registration_number": r["registration_number"], "phone": r["phone"], "email": r["email"],
            "address": r["address"], "postal_code": r["postal_code"], "is_active": r["is_active"],
            "created_at": format_ts(r["created_at"]), "updated_at": format_ts(r["updated_at"])}


def product(r) -> dict:
    return {"id": _s(r["id"]), "code": r["code"], "name": r["name"], "description": r["description"],
            "category": {"id": _s(r["category_id"]), "code": r["category_code"], "name": r["category_name"]},
            "default_unit": {"id": _s(r["default_unit_id"]), "code": r["unit_code"], "name": r["unit_name"],
                             "unit_type": r["unit_type"]},
            "is_active": r["is_active"], "created_at": format_ts(r["created_at"]), "updated_at": format_ts(r["updated_at"])}


def category(r) -> dict:
    return {"id": _s(r["id"]), "code": r["code"], "name": r["name"], "parent_id": _s(r["parent_id"]), "is_active": r["is_active"]}


def unit(r) -> dict:
    return {"id": _s(r["id"]), "code": r["code"], "name": r["name"], "unit_type": r["unit_type"], "is_active": r["is_active"]}


def spec_value(r):
    """Stored product value -> the canonical JSON value of contract section 12 (same forms the snapshot uses)."""
    t = r["data_type"]
    if t == "TEXT":
        return r["value_text"]
    if t == "NUMBER":
        return None if r["value_number"] is None else str(r["value_number"])
    if t == "DECIMAL":
        v = r["value_decimal"]
        if v is None:
            return None
        s = format(v, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        if s in ("-0", ""):
            s = "0"
        return s
    if t == "BOOLEAN":
        return r["value_boolean"]
    if t == "DATE":
        return None if r["value_date"] is None else r["value_date"].isoformat()
    if t == "SELECT":
        return r["value_option"]
    return r["value_options"]                    # MULTI_SELECT: JSONB list


# ---------------------------------------------------------------------------- purchase requests (stage 3)
def _money(v) -> str:
    return str(Decimal(v).quantize(Decimal(1)))


def _fixed3(v):
    return None if v is None else format(Decimal(v).quantize(Decimal("0.001")), "f")


def request_header(r) -> dict:
    d = {"id": _s(r["id"]), "request_number": r["request_number"], "status": r["status"],
         "customer": {"id": _s(r["customer_id"]), "name": r["customer_name"]},
         "request_date": format_ts(r["request_date"]),
         "requested_delivery_date": None if r["requested_delivery_date"] is None else r["requested_delivery_date"].isoformat(),
         "subtotal": _money(r["subtotal"]), "discount_total": _money(r["discount_total"]),
         "tax_total": _money(r["tax_total"]), "grand_total": _money(r["grand_total"]), "notes": r["notes"],
         "created_by": _s(r["created_by"]), "updated_by": _s(r["updated_by"]),
         "created_at": format_ts(r["created_at"]), "updated_at": format_ts(r["updated_at"])}
    if "item_count" in r:
        d["item_count"] = int(r["item_count"])
    return d


def request_item(r) -> dict:
    return {"id": _s(r["id"]), "purchase_request_id": _s(r["purchase_request_id"]),
            "product": {"id": _s(r["product_id"]), "code": r["product_code"], "name": r["product_name"]},
            "unit": {"id": _s(r["unit_id"]), "code": r["unit_code"], "name": r["unit_name"]},
            "quantity": _fixed3(r["quantity"]), "bundle_count": _money(r["bundle_count"]),
            "estimated_weight": _fixed3(r["estimated_weight"]),
            "unit_price": _money(r["unit_price"]), "discount_amount": _money(r["discount_amount"]),
            "tax_amount": _money(r["tax_amount"]), "line_total": _money(r["line_total"]),
            "notes": r["notes"], "specifications": r["specifications"],
            "created_at": format_ts(r["created_at"]), "updated_at": format_ts(r["updated_at"])}


def audit_row(r) -> dict:
    return {"id": _s(r["id"]), "user_id": _s(r["user_id"]), "entity_type": r["entity_type"], "entity_id": _s(r["entity_id"]),
            "action": r["action"], "old_data": r["old_data"], "new_data": r["new_data"], "description": r["description"],
            "ip_address": _s(r["ip_address"]), "created_at": format_ts(r["created_at"])}


# ---------------------------------------------------------------------------- pre-invoices (stage 4)
def _ts(v):
    return None if v is None else format_ts(v)


def pre_invoice_document(d) -> dict | None:
    """Metadata of the PDF row. The bytes are never serialized here."""
    if d is None:
        return None
    return {"status": d["status"], "size": d["pdf_size"], "sha256": d["pdf_sha256"], "template_version": d["template_version"],
            "generated_at": _ts(d["generated_at"]), "attempt_count": d["attempt_count"],
            "last_attempt_at": _ts(d["last_attempt_at"]), "last_error_code": d["last_error_code"]}


def pre_invoice_item(r) -> dict:
    return {"id": _s(r["id"]), "line_no": r["line_no"], "source_item_id": _s(r["source_item_id"]),
            "product": {"id": _s(r["product_id"]), "code": r["product_code"], "name": r["product_name"]},
            "unit": {"id": _s(r["unit_id"]), "code": r["unit_code"], "name": r["unit_name"]},
            "quantity": _fixed3(r["quantity"]), "bundle_count": _money(r["bundle_count"]),
            "estimated_weight": _fixed3(r["estimated_weight"]),
            "unit_price": _money(r["unit_price"]), "discount_amount": _money(r["discount_amount"]),
            "tax_amount": _money(r["tax_amount"]), "line_total": _money(r["line_total"]),
            "notes": r["notes"], "specifications": r["specifications"]}


def pre_invoice(r, document=None) -> dict:
    d = {"id": _s(r["id"]), "status": r["status"], "pre_invoice_number": r["pre_invoice_number"], "version": r["version"],
         "chain_id": _s(r["chain_id"]), "supersedes_id": _s(r["supersedes_id"]),
         "source_request": {"id": _s(r["source_request_id"]), "request_number": r["request_number"]},
         "request": {"date": format_ts(r["request_date"]),
                     "requested_delivery_date": None if r["requested_delivery_date"] is None else r["requested_delivery_date"].isoformat(),
                     "notes": r["request_notes"]},
         "seller": {"name": r["seller_name"], "legal_name": r["seller_legal_name"], "national_id": r["seller_national_id"],
                    "economic_code": r["seller_economic_code"], "registration_number": r["seller_registration_number"],
                    "phone": r["seller_phone"], "email": r["seller_email"], "address": r["seller_address"],
                    "postal_code": r["seller_postal_code"]},
         "customer": {"id": _s(r["customer_id"]), "customer_type": r["customer_type"],
                      "name": r["customer_name"], "national_id": r["customer_national_id"],
                      "economic_code": r["customer_economic_code"], "registration_number": r["customer_registration_number"],
                      "mobile": r["customer_mobile"], "phone": r["customer_phone"], "email": r["customer_email"],
                      "address": r["customer_address"], "postal_code": r["customer_postal_code"]},
         "subtotal": _money(r["subtotal"]), "discount_total": _money(r["discount_total"]),
         "tax_total": _money(r["tax_total"]), "grand_total": _money(r["grand_total"]),
         "created_by": _s(r["created_by"]), "created_at": format_ts(r["created_at"]),
         "issued_by": _s(r["issued_by"]), "issued_at": _ts(r["issued_at"]), "superseded_at": _ts(r["superseded_at"]),
         "cancelled_by": _s(r["cancelled_by"]), "cancelled_at": _ts(r["cancelled_at"]), "cancel_reason": r["cancel_reason"],
         "updated_at": format_ts(r["updated_at"]),
         "pdf": pre_invoice_document(document)}
    return d
