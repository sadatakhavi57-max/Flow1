"""Organizations, customers, products, specifications and the two lookups."""
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from tradeflow_core.inputs import data_envelope, list_envelope

from ..http_utils import API, client_ip, page, read_json, rid


def build(ctx) -> APIRouter:
    r = APIRouter(prefix=API)
    customers, products = ctx.customers, ctx.products

    @r.get("/organizations")
    async def organizations(request: Request):
        p = await ctx.principal(request)
        org = await run_in_threadpool(products.organization, p)
        return {**list_envelope([org], 1, 50, 1), "request_id": rid(request)}

    @r.get("/organizations/{oid}")
    async def organization(request: Request, oid: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(products.organization, p, oid), rid(request))

    @r.get("/customers")
    async def customers_list(request: Request):
        p = await ctx.principal(request)
        return page(request, await run_in_threadpool(customers.list, p, request.query_params))

    @r.post("/customers", status_code=201)
    async def customers_create(request: Request):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(customers.create, p, body, client_ip(request)), rid(request))

    @r.get("/customers/{cid}")
    async def customers_get(request: Request, cid: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(customers.get, p, cid), rid(request))

    @r.patch("/customers/{cid}")
    async def customers_patch(request: Request, cid: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(customers.patch, p, cid, body, client_ip(request)), rid(request))

    @r.get("/products")
    async def products_list(request: Request):
        p = await ctx.principal(request)
        return page(request, await run_in_threadpool(products.list, p, request.query_params))

    @r.post("/products", status_code=201)
    async def products_create(request: Request):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(products.create, p, body, client_ip(request)), rid(request))

    @r.get("/products/{pid}")
    async def products_get(request: Request, pid: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(products.get, p, pid), rid(request))

    @r.patch("/products/{pid}")
    async def products_patch(request: Request, pid: str):
        p = await ctx.principal(request)
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(products.patch, p, pid, body, client_ip(request)), rid(request))

    @r.get("/products/{pid}/specifications")
    async def products_specs(request: Request, pid: str):
        p = await ctx.principal(request)
        return data_envelope(await run_in_threadpool(products.specifications, p, pid), rid(request))

    @r.get("/product-categories")
    async def categories(request: Request):
        p = await ctx.principal(request)
        return page(request, await run_in_threadpool(products.categories, p, request.query_params))

    @r.get("/units")
    async def units(request: Request):
        p = await ctx.principal(request)
        return page(request, await run_in_threadpool(products.units, p, request.query_params))

    return r
