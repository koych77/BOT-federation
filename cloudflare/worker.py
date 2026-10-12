"""Cloudflare Workers entrypoint for the federation bot migration."""

from fastapi import FastAPI, Request
from fastapi.responses import Response
from workers import asgi


app = FastAPI(title="Federation Bot (Cloudflare)")
Default = asgi.entrypoint(app)


@app.get("/health")
async def health(request: Request) -> dict:
    result = await request.scope["env"].DB.prepare("SELECT 1 AS ok").first()
    return {"ok": True, "database": "d1", "query": int(result.ok)}


@app.get("/{path:path}")
async def frontend(path: str, request: Request) -> Response:
    asset_path = path or "index.html"
    response = await request.scope["env"].ASSETS.fetch(
        f"https://assets.local/{asset_path}"
    )
    return Response(
        content=await response.bytes(),
        status_code=response.status,
        headers=dict(response.headers),
    )
