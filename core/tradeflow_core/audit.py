"""Audit vocabulary and safety - contract section 13 (D4). The database has no CHECK; these enums are the guard."""
from __future__ import annotations

from enum import Enum

from .errors import AppError, ErrorCode


class AuditAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SUBMIT = "SUBMIT"
    CANCEL = "CANCEL"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    ISSUE = "ISSUE"                      # Stage 4 (contract section 26)
    SUPERSEDE = "SUPERSEDE"
    PDF_GENERATE = "PDF_GENERATE"
    PDF_FAIL = "PDF_FAIL"


class AuditEntity(str, Enum):
    USER = "USER"
    CUSTOMER = "CUSTOMER"
    PRODUCT = "PRODUCT"
    PURCHASE_REQUEST = "PURCHASE_REQUEST"
    PURCHASE_REQUEST_ITEM = "PURCHASE_REQUEST_ITEM"
    PRE_INVOICE = "PRE_INVOICE"


FORBIDDEN_KEYS = frozenset({"password", "password_hash", "token", "token_hash", "access_token", "refresh_token",
                            "secret", "authorization"})


def _scan(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"forbidden key {k!r} in audit data at {path}")
            _scan(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _scan(v, f"{path}[{i}]")


def build_entry(action: str, entity_type: str, *, organization_id: str, user_id: str | None, entity_id: str | None,
                old_data=None, new_data=None, description: str | None = None, ip_address: str | None = None) -> dict:
    """The only way to make an audit row. Unknown action/entity strings and secrets raise (a bug, never a client error)."""
    a = AuditAction(action)            # ValueError on anything outside the closed sets
    e = AuditEntity(entity_type)
    _scan(old_data); _scan(new_data)
    if not organization_id:
        raise ValueError("audit_logs.organization_id is mandatory")
    return {"organization_id": organization_id, "user_id": user_id, "action": a.value, "entity_type": e.value,
            "entity_id": entity_id, "old_data": old_data, "new_data": new_data,
            "description": description, "ip_address": ip_address}
