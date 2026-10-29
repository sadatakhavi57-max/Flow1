"""Pre-invoices (Stage 4): DRAFT, issue, cancel, PDF."""
from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from tradeflow_core.inputs import data_envelope

from ..http_utils import API, client_ip, page, read_json, rid


def build(ctx) -> APIRouter:
    r = APIRouter(prefix=API)
    svc = ctx.pre_invoices

    @r.post("/purchase-requests/{req_id}/pre-invoices", status_code=201)
    async def pi_create(request: Request, req_id: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(svc.create, p, req_id, body, client_ip(request)), rid(request))

    @r.get("/pre-invoices")
    async def pi_list(request: Request):
        p = await ctx.principal(request)
        return page(request, await run_in_threadpool(svc.list, p, request.query_params))

    @r.get("/pre-invoices/{pid}")
    async def pi_get(request: Request, pid: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(svc.get, p, pid), rid(request))

    @r.post("/pre-invoices/{pid}/issue")
    async def pi_issue(request: Request, pid: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(svc.issue, p, pid, client_ip(request)), rid(request))

    @r.post("/pre-invoices/{pid}/cancel")
    async def pi_cancel(request: Request, pid: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(svc.cancel, p, pid, body, client_ip(request)), rid(request))

    @r.post("/pre-invoices/{pid}/pdf")
    async def pi_pdf_generate(request: Request, pid: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(svc.generate_pdf, p, pid, client_ip(request)), rid(request))

    @r.get("/pre-invoices/{pid}/pdf")
    async def pi_pdf_download(request: Request, pid: str):
        p = await ctx.principal(request)
        filename, data, sha = await run_in_threadpool(svc.download_pdf, p, pid)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"', "ETag": f'"{sha}"',
                                 "Cache-Control": "private, no-store"})

    return r
