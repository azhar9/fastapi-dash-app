from __future__ import annotations

from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, Query

from ..cache import Cache, cached
from ..db import fetch, load_sql
from ..deps import get_cache, get_pool
from ..schemas import ReturnPoint, RollingMetricPoint

router = APIRouter(prefix="/portfolios/{portfolio_id}/performance", tags=["performance"])


@router.get("/vs-benchmark", response_model=list[ReturnPoint])
async def vs_benchmark(
    portfolio_id: int,
    start: date | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> list[dict]:
    return await _vs_bench(pool, cache, portfolio_id, start)


@cached("performance.vs_bench", ttl=300)
async def _vs_bench(pool: asyncpg.Pool, cache: Cache, portfolio_id: int, start: date | None) -> list[dict]:
    return await fetch(pool, load_sql("performance/cum_returns_vs_bench.sql"), portfolio_id, start)


@router.get("/rolling", response_model=list[RollingMetricPoint])
async def rolling(
    portfolio_id: int,
    window_days: int = Query(60, ge=5, le=252),
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> list[dict]:
    return await _rolling(pool, cache, portfolio_id, window_days)


@cached("performance.rolling", ttl=300)
async def _rolling(pool: asyncpg.Pool, cache: Cache, portfolio_id: int, window_days: int) -> list[dict]:
    return await fetch(pool, load_sql("performance/rolling_metrics.sql"), portfolio_id, window_days)
