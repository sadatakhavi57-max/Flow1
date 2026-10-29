from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from ..http_utils import API, page


def build(ctx) -> APIRouter:
    r = APIRouter(prefix=API)

    @r.get("/audit-logs")
    async def audit_logs(request: Request):
        p = await ctx.principal(request)
        return page(request, await run_in_threadpool(ctx.audits.list, p, request.query_params))

    return r
