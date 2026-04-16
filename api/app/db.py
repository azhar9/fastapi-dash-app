"""asyncpg connection pool and a thin helper that loads .sql files from disk.

Why raw SQL in .sql files:
  - The queries themselves are the interesting part of this codebase;
    keeping them out of Python string literals makes them grep-able and
    diff-friendly.
  - Query files are read once at startup and cached in memory, so there's
    no per-request filesystem cost.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import asyncpg

log = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"
_sql_cache: dict[str, str] = {}


def load_sql(name: str) -> str:
    """Load a SQL file by relative name, e.g. 'performance/nav_series.sql'."""
    if name in _sql_cache:
        return _sql_cache[name]
    path = SQL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    text = path.read_text(encoding="utf-8")
    _sql_cache[name] = text
    return text


async def create_pool(dsn: str) -> asyncpg.Pool:
    # min_size=1 keeps at least one warm connection so the first request
    # doesn't pay the TCP + auth round-trip. max_size caps parallel load.
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )
    log.info("pg pool ready", extra={"min_size": 1, "max_size": 10})
    return pool


async def fetch(pool: asyncpg.Pool, sql: str, *args: Any) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]


async def fetchrow(pool: asyncpg.Pool, sql: str, *args: Any) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, *args)
        return dict(row) if row else None
