"""POST /ask — natural-language query endpoint.

Pipeline:
    question (str)
      → LLM → {sql, chart_type, ...}
      → structural validation (SELECT-only, no ';' stacking, LIMIT cap)
      → execute on the read-only asyncpg pool with a per-statement timeout
      → return SQL, rows, chart hints

Three independent safety layers:
  1. Banned-keyword / single-statement check (fast fail, no DB round-trip).
  2. statement_timeout set via `SET LOCAL` on the transaction.
  3. Dedicated app_ro PG role — SELECT grants only. Even a slip in the
     upper layers hits a permission denial.
"""
from __future__ import annotations

import logging
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import get_llm, get_ro_pool
from ..errors import AppError
from ..llm import LlmClient, LlmError
from ..sqlguard import SqlSafetyError, sanitise

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=400)


class AskApiResponse(BaseModel):
    question: str
    sql: str
    explanation: str
    chart_type: str
    x_col: str | None
    y_col: str | None
    title: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class ServiceUnavailable(AppError):
    status_code = 503
    title = "Service Unavailable"


@router.post("", response_model=AskApiResponse)
async def ask(
    req: AskRequest,
    pool: asyncpg.Pool = Depends(get_ro_pool),
    llm: LlmClient | None = Depends(get_llm),
) -> AskApiResponse:
    if llm is None:
        raise ServiceUnavailable(
            "LLM is not configured. Set GROQ_API_KEY in the server environment."
        )

    try:
        plan = llm.ask(req.question)
    except LlmError as e:
        raise AppError(str(e)) from e

    try:
        clean_sql = sanitise(plan.sql)
    except SqlSafetyError as e:
        log.warning("rejected llm sql: %s | sql=%r", e, plan.sql)
        raise AppError(f"Generated SQL was not safe to run: {e}") from e

    log.info("ask executing", extra={"question": req.question, "sql": clean_sql})

    # Per-request statement_timeout. The RO role already has a 10s default,
    # but a tighter per-query cap stops a single slow plan from holding a
    # connection for longer than the UI would wait anyway.
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = '5s'")
            try:
                records = await conn.fetch(clean_sql)
            except asyncpg.PostgresError as e:
                log.info("ask sql rejected by pg", extra={"sqlstate": getattr(e, "sqlstate", None)})
                raise AppError(f"Postgres rejected the query: {e.__class__.__name__}") from e

    columns = list(records[0].keys()) if records else []
    rows    = [dict(r) for r in records]

    return AskApiResponse(
        question=req.question,
        sql=clean_sql,
        explanation=plan.explanation,
        chart_type=plan.chart_type,
        x_col=plan.x_col,
        y_col=plan.y_col,
        title=plan.title,
        columns=columns,
        rows=rows,
        row_count=len(rows),
    )
