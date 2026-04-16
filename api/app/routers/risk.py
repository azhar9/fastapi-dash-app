from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query

from ..cache import Cache, cached
from ..db import fetchrow, load_sql
from ..deps import get_cache, get_pool
from ..errors import NotFoundError
from ..schemas import RiskMetrics

router = APIRouter(prefix="/portfolios/{portfolio_id}/risk", tags=["risk"])


@router.get("", response_model=RiskMetrics)
async def risk_metrics(
    portfolio_id: int,
    window_days: int = Query(365, ge=30, le=3650),
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> dict:
    row = await _risk(pool, cache, portfolio_id, window_days)
    if row is None:
        raise NotFoundError(f"No risk data available for portfolio {portfolio_id}")
    return row


@cached("risk.metrics", ttl=600)
async def _risk(pool: asyncpg.Pool, cache: Cache, portfolio_id: int, window_days: int) -> dict | None:
    return await fetchrow(pool, load_sql("risk/risk_metrics.sql"), portfolio_id, window_days)
