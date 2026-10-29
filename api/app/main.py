"""FastAPI application factory: middleware, error handlers, wiring. Routes live in app/routes/*."""
from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from tradeflow_core.errors import AppError, ErrorCode

from . import db as dbmod
from .audit_service import AuditService
from .auth_service import AuthService
from .customers_service import CustomerService
from .http_utils import error_response, rid
from .pre_invoices_service import PreInvoiceService
from .products_service import ProductService
from .requests_service import RequestService
from .routes import (audit as audit_routes, auth as auth_routes, master as master_routes, pre_invoices as pre_invoice_routes,
                     requests as request_routes)

log = logging.getLogger("tradeflow")


def create_app(settings, db=None, limiter=None, clock=None, pdf_renderer=None) -> FastAPI:
    app = FastAPI(title="TradeFlow API", docs_url=None, redoc_url=None, openapi_url=None)
    db = db or dbmod.Database(settings.database_dsn)
    kw = {"clock": clock} if clock else {}
    auth = AuthService(db, settings, limiter, **kw)
    app.state.db, app.state.auth, app.state.settings = db, auth, settings
    for w in settings.warnings:
        log.warning(w)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error request_id=%s", request.state.request_id)
            response = error_response(request, AppError(ErrorCode.INTERNAL_ERROR))
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(AppError)
    async def _app_error(request, exc: AppError):
        return error_response(request, exc)

    @app.exception_handler(psycopg.Error)
    async def _pg_error(request, exc):
        err = dbmod.to_app_error(exc)
        if err.code is ErrorCode.INTERNAL_ERROR:
            log.error("database error request_id=%s sqlstate=%s", rid(request), getattr(exc, "sqlstate", None))
        return error_response(request, err)

    @app.exception_handler(RequestValidationError)
    async def _validation(request, exc):
        return error_response(request, AppError(ErrorCode.VALIDATION_ERROR, details=[{"field": "$", "reason": "INVALID_REQUEST"}]))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request, exc):
        """Unknown route -> 404 NOT_FOUND; wrong method etc. keep their HTTP status (405 + Allow) inside the standard envelope."""
        err = AppError(ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.MALFORMED_REQUEST)
        return JSONResponse(err.to_body(rid(request)), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    async def principal(request: Request):
        return await run_in_threadpool(auth.authenticate, request.headers.get("authorization"))

    ctx = SimpleNamespace(auth=auth, principal=principal, customers=CustomerService(db), products=ProductService(db),
                          requests=RequestService(db, **kw), audits=AuditService(db),
                          pre_invoices=PreInvoiceService(db, pdf_renderer, **kw))
    for module in (auth_routes, master_routes, request_routes, pre_invoice_routes, audit_routes):
        app.include_router(module.build(ctx))
    app.state.principal = principal
    return app
