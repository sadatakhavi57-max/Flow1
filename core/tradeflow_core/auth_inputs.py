"""Login and logout inputs - contract section 3."""
from __future__ import annotations

from . import inputs
from .digits import normalize_digits
from .passwords import MAX_PASSWORD_BYTES


def parse_login(body) -> tuple[str, str, str]:
    """-> (organization_code upper-cased + digits ASCII, username trimmed + lower-cased, password unchanged).
    A badly shaped body is a 422; a well-shaped but unknown organization/user is decided by the Service as the single
    401 AUTH_INVALID_CREDENTIALS (so the format of organization_code is deliberately NOT validated here)."""
    inputs.strict_object(body, ("organization_code", "username", "password"), required=("organization_code", "username", "password"))
    for f in ("organization_code", "username", "password"):
        if not isinstance(body[f], str):
            raise inputs.verr(f, "MUST_BE_STRING")
    org = normalize_digits(body["organization_code"].strip()).upper()
    user = body["username"].strip().lower()
    pw = body["password"]
    if not org or len(org) > 50:
        raise inputs.verr("organization_code", "LENGTH_1_TO_50")
    if not user or len(user) > 100:
        raise inputs.verr("username", "LENGTH_1_TO_100")
    if not pw or len(pw.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise inputs.verr("password", "LENGTH_1_TO_1024_BYTES")
    return org, user, pw


def parse_refresh_body(body) -> str:
    inputs.strict_object(body, ("refresh_token",), required=("refresh_token",))
    t = body["refresh_token"]
    if not isinstance(t, str) or not t or len(t) > 256:
        raise inputs.verr("refresh_token", "INVALID")
    return t
