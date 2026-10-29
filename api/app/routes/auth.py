from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from tradeflow_core.inputs import data_envelope

from ..http_utils import API, client_ip, read_json, rid


def build(ctx) -> APIRouter:
    r = APIRouter(prefix=f"{API}/auth")

    @r.post("/login")
    async def login(request: Request):
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(ctx.auth.login, body, client_ip(request)), rid(request))

    @r.post("/refresh")
    async def refresh(request: Request):
        body = await read_json(request)
        return data_envelope(await run_in_threadpool(ctx.auth.refresh, body), rid(request))

    @r.post("/logout")
    async def logout(request: Request):
        p = await ctx.principal(request)
        body = await read_json(request)
        await run_in_threadpool(ctx.auth.logout, p, body, client_ip(request))
        return Response(status_code=204)

    @r.get("/me")
    async def me(request: Request):
        p = await ctx.principal(request)
        return data_envelope(p.user_json(), rid(request))

    return r
