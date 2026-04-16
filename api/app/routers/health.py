from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from ..cache import Cache
from ..deps import get_cache, get_pool

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness probe — process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> dict:
    """Readiness — we can reach Postgres and Redis."""
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    cache_ok = await cache.ping()
    return {"status": "ok", "postgres": True, "redis": cache_ok}
