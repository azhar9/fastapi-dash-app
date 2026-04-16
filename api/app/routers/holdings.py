from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from ..cache import Cache, cached
from ..db import fetch, load_sql
from ..deps import get_cache, get_pool
from ..schemas import HoldingRow, SectorSlice

router = APIRouter(prefix="/portfolios/{portfolio_id}/holdings", tags=["holdings"])


@router.get("", response_model=list[HoldingRow])
async def holdings(
    portfolio_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> list[dict]:
    return await _holdings(pool, cache, portfolio_id)


@cached("holdings.list", ttl=300)
async def _holdings(pool: asyncpg.Pool, cache: Cache, portfolio_id: int) -> list[dict]:
    return await fetch(pool, load_sql("holdings/breakdown.sql"), portfolio_id)


@router.get("/sectors", response_model=list[SectorSlice])
async def sectors(
    portfolio_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
    cache: Cache = Depends(get_cache),
) -> list[dict]:
    return await _sectors(pool, cache, portfolio_id)


@cached("holdings.sectors", ttl=300)
async def _sectors(pool: asyncpg.Pool, cache: Cache, portfolio_id: int) -> list[dict]:
    return await fetch(pool, load_sql("holdings/sector_breakdown.sql"), portfolio_id)
