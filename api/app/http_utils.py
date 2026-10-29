"""Helpers shared by main.py and the routers (no routes here)."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from tradeflow_core.errors import AppError, ErrorCode
from tradeflow_core.inputs import list_envelope

API = "/api/v1"


def rid(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def error_response(request: Request, err: AppError) -> JSONResponse:
    headers = {}
    if err.code is ErrorCode.RATE_LIMITED and getattr(err, "retry_after", None):
        headers["Retry-After"] = str(err.retry_after)
    return JSONResponse(err.to_body(rid(request)), status_code=err.http_status, headers=headers)


async def read_json(request: Request):
    """Contract 15: a body that is not JSON, or is sent with a non-JSON Content-Type, is 400 MALFORMED_REQUEST."""
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media != "application/json" and not (media.startswith("application/") and media.endswith("+json")):
        raise AppError(ErrorCode.MALFORMED_REQUEST, details={"reason": "CONTENT_TYPE_MUST_BE_JSON"})
    try:
        return await request.json()
    except Exception:
        raise AppError(ErrorCode.MALFORMED_REQUEST)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def page(request: Request, result) -> dict:
    items, pg, size, total = result
    return {**list_envelope(items, pg, size, total), "request_id": rid(request)}
