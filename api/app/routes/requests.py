"""Purchase requests, items, pricing."""
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from tradeflow_core.inputs import data_envelope

from ..http_utils import API, client_ip, page, read_json, rid


def build(ctx) -> APIRouter:
    r = APIRouter(prefix=API)
    reqs = ctx.requests

    @r.get("/purchase-requests")
    async def pr_list(request: Request):
        p = await ctx.principal(request)
        return page(request, await run_in_threadpool(reqs.list, p, request.query_params))

    @r.post("/purchase-requests", status_code=201)
    async def pr_create(request: Request):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(reqs.create, p, body, client_ip(request)), rid(request))

    @r.get("/purchase-requests/{req_id}")
    async def pr_get(request: Request, req_id: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(reqs.get, p, req_id), rid(request))

    @r.patch("/purchase-requests/{req_id}")
    async def pr_patch(request: Request, req_id: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(reqs.patch, p, req_id, body, client_ip(request)), rid(request))

    @r.post("/purchase-requests/{req_id}/submit")
    async def pr_submit(request: Request, req_id: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(reqs.submit, p, req_id, client_ip(request)), rid(request))

    @r.post("/purchase-requests/{req_id}/cancel")
    async def pr_cancel(request: Request, req_id: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(reqs.cancel, p, req_id, body, client_ip(request)), rid(request))

    @r.post("/purchase-requests/{req_id}/items", status_code=201)
    async def pr_add_item(request: Request, req_id: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(reqs.add_item, p, req_id, body, client_ip(request)), rid(request))

    @r.patch("/purchase-request-items/{item_id}")
    async def pri_patch(request: Request, item_id: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(reqs.patch_item, p, item_id, body, client_ip(request)), rid(request))

    @r.delete("/purchase-request-items/{item_id}")
    async def pri_delete(request: Request, item_id: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(reqs.delete_item, p, item_id, client_ip(request)), rid(request))

    @r.get("/purchase-requests/{req_id}/pricing")
    async def pricing_get(request: Request, req_id: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(reqs.get_pricing, p, req_id), rid(request))

    @r.post("/purchase-requests/{req_id}/pricing")
    async def pricing_set(request: Request, req_id: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(reqs.set_pricing, p, req_id, body, client_ip(request)), rid(request))

    return r
