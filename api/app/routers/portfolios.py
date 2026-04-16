from __future__ import annotations

from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, Query

from ..cache import Cache, cached
from ..db import fetch, fetchrow, load_sql
from ..deps import get_cache, get_pool
from ..errors import NotFoundError
from ..schemas import KpiSummary, NavPoint, Portfolio

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=list[Portfolio])
async def list_portfolios(
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> list[dict]:
    return await _list(pool, cache)


@cached("portfolios.list", ttl=600)
async def _list(pool: asyncpg.Pool, cache: Cache) -> list[dict]:
    return await fetch(pool, load_sql("portfolios/list.sql"))


@router.get("/{portfolio_id}/kpis", response_model=KpiSummary)
async def kpi_summary(
    portfolio_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> dict:
    row = await _kpis(pool, cache, portfolio_id)
    if row is None or row.get("nav") is None:
        raise NotFoundError(f"No NAV data for portfolio {portfolio_id}")
    return row


@cached("portfolios.kpis", ttl=300)
async def _kpis(pool: asyncpg.Pool, cache: Cache, portfolio_id: int) -> dict | None:
    return await fetchrow(pool, load_sql("portfolios/kpi_summary.sql"), portfolio_id)


@router.get("/{portfolio_id}/nav", response_model=list[NavPoint])
async def nav_series(
    portfolio_id: int,
    start: date | None = Query(None, description="Inclusive start date; omit for full history."),
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> list[dict]:
    return await _nav(pool, cache, portfolio_id, start)


@cached("portfolios.nav", ttl=300)
async def _nav(pool: asyncpg.Pool, cache: Cache, portfolio_id: int, start: date | None) -> list[dict]:
    return await fetch(pool, load_sql("portfolios/nav_series.sql"), portfolio_id, start)
