"""Small SQL helpers shared by the services."""
from __future__ import annotations

from tradeflow_core import audit, inputs
from tradeflow_core.errors import AppError, ErrorCode

from . import auth_repo


def like_pattern(term: str) -> str:
    """Contains-pattern with LIKE metacharacters escaped (used with ESCAPE '\\')."""
    esc = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def not_found(resource: str) -> AppError:
    return AppError(ErrorCode.NOT_FOUND, details={"resource": resource})


def write_audit(conn, principal, action: str, entity: str, entity_id, *, old=None, new=None, description=None, ip=None):
    auth_repo.insert_audit(conn, audit.build_entry(action, entity, organization_id=principal.org_id, user_id=principal.user_id,
                                                   entity_id=entity_id, old_data=old, new_data=new,
                                                   description=description, ip_address=ip))


def page_args(query) -> tuple[int, int, int]:
    page, size = inputs.parse_pagination(query.get("page"), query.get("page_size"))
    return page, size, (page - 1) * size
