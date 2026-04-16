"""Natural-language → SQL via a Groq-hosted Llama model.

Groq exposes an OpenAI-compatible API, so we use the official OpenAI SDK
with a custom base_url. The model is asked to return strict JSON, which
makes parsing trivial and lets the /ask router run structural validation
on the SQL before ever sending it to Postgres.

Design choices:
  * The schema block is *hand-curated*, not introspected from PG. A
    curated prompt is shorter, more relevant, and stops the model from
    inventing plausible-but-wrong columns.
  * We include three small few-shot examples. This anchors output shape
    and pushes the model toward idiomatic PG (window functions, CTEs).
  * Response is JSON-mode so we don't need regex scraping.
"""
from __future__ import annotations

import json
import logging
import os

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)


class AskResponse(BaseModel):
    sql: str = Field(..., description="A single SELECT statement.")
    explanation: str = Field("", description="One-line description of what the query returns.")
    chart_type: str = Field("none", description="One of: line | bar | pie | none.")
    x_col: str | None = Field(None, description="Name of the column to use on the x-axis.")
    y_col: str | None = Field(None, description="Name of the column to use on the y-axis.")
    title: str = Field("", description="Chart title.")


SCHEMA_BLOCK = """\
You write SQL for a PostgreSQL 16 database supporting a portfolio-performance
reporting dashboard for an asset management firm. The schema is:

  securities (ticker PK, name, sector, asset_class, currency)
  prices (ticker FK, as_of_date, open, high, low, close, adj_close, volume)
    -- PK (ticker, as_of_date). Daily bars since 2022-01-03. Prices are USD.

  benchmark_prices (benchmark, as_of_date, close, adj_close)
    -- PK (benchmark, as_of_date). Currently only 'SPY' is loaded.

  portfolios (portfolio_id PK, code, name, strategy, benchmark, inception, base_ccy)
    -- Three rows: GAM_CORE, GAM_TECH, GAM_DIVIDEND. All benchmark = 'SPY'.

  holdings (portfolio_id FK, ticker FK, weight, valid_from, valid_to)
    -- weight is a fraction in [0, 1]. valid_to NULL means 'still held'.

  portfolio_nav (portfolio_id, as_of_date, nav)
    -- MATERIALIZED VIEW. Daily weighted-close NAV per portfolio.
    -- Use this whenever the user asks about NAV, returns, or performance.

Available sectors: Technology, Communication Services, Consumer Discretionary,
Consumer Staples, Financials, Health Care, Energy.
"""

FEW_SHOTS = [
    {
        "user": "Top 5 holdings in the Tech portfolio by weight.",
        "out": {
            "sql": (
                "SELECT s.ticker, s.name, (h.weight * 100)::numeric(6,2) AS weight_pct "
                "FROM holdings h "
                "JOIN portfolios p ON p.portfolio_id = h.portfolio_id "
                "JOIN securities s ON s.ticker = h.ticker "
                "WHERE p.code = 'GAM_TECH' AND h.valid_to IS NULL "
                "ORDER BY h.weight DESC LIMIT 5"
            ),
            "explanation": "Current holdings in GAM_TECH, ordered by weight.",
            "chart_type": "bar", "x_col": "ticker", "y_col": "weight_pct",
            "title": "Top 5 holdings by weight — GAM Tech",
        },
    },
    {
        "user": "Show me the NAV of GAM_CORE over time.",
        "out": {
            "sql": (
                "SELECT pn.as_of_date, pn.nav "
                "FROM portfolio_nav pn "
                "JOIN portfolios p USING (portfolio_id) "
                "WHERE p.code = 'GAM_CORE' "
                "ORDER BY pn.as_of_date"
            ),
            "explanation": "Daily NAV series for the Core portfolio.",
            "chart_type": "line", "x_col": "as_of_date", "y_col": "nav",
            "title": "NAV — GAM Core",
        },
    },
    {
        "user": "Sector breakdown of the dividend portfolio.",
        "out": {
            "sql": (
                "SELECT s.sector, (SUM(h.weight) * 100)::numeric(6,2) AS weight_pct "
                "FROM holdings h "
                "JOIN portfolios p  ON p.portfolio_id = h.portfolio_id "
                "JOIN securities s  ON s.ticker      = h.ticker "
                "WHERE p.code = 'GAM_DIVIDEND' AND h.valid_to IS NULL "
                "GROUP BY s.sector ORDER BY weight_pct DESC"
            ),
            "explanation": "Current sector weights of GAM_DIVIDEND.",
            "chart_type": "pie", "x_col": "sector", "y_col": "weight_pct",
            "title": "Sector breakdown — GAM Dividend",
        },
    },
]

SYSTEM_PROMPT = f"""\
You convert a user's natural-language question into a single read-only SQL
query against a known Postgres schema, plus a hint about how to visualise
the result.

{SCHEMA_BLOCK}

Rules — these are hard constraints, not suggestions:
  1. Emit exactly one statement. It MUST start with SELECT or WITH. Never
     DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, GRANT, CREATE, COPY.
  2. Do not include a trailing semicolon.
  3. If the query could be unbounded, always include LIMIT 1000 or smaller.
  4. Reference only tables/columns listed above. If the question cannot be
     answered, still emit a valid SELECT that returns an empty result — do
     NOT invent columns.
  5. Prefer window functions (LAG, AVG OVER, FIRST_VALUE) over correlated
     subqueries.
  6. chart_type must be one of: line, bar, pie, none.
  7. For time-series answers use chart_type=line, x_col=as_of_date.
  8. For rankings / categorical comparisons use chart_type=bar.
  9. For composition (percentages summing to 100) use chart_type=pie.
 10. If the result isn't naturally visual (e.g. a single scalar) use none.

Return ONLY a JSON object with these keys: sql, explanation, chart_type,
x_col, y_col, title. No markdown fences, no commentary.
"""


class LlmError(Exception):
    pass


class LlmClient:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.groq.com/openai/v1") -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def ask(self, question: str) -> AskResponse:
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for shot in FEW_SHOTS:
            messages.append({"role": "user",      "content": shot["user"]})
            messages.append({"role": "assistant", "content": json.dumps(shot["out"])})
        messages.append({"role": "user", "content": question})

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            log.warning("llm call failed: %s", e)
            raise LlmError(f"LLM call failed: {e.__class__.__name__}") from e

        raw = completion.choices[0].message.content or ""
        try:
            data = json.loads(raw)
            return AskResponse.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("llm returned unparseable JSON: %s\n%s", e, raw[:500])
            raise LlmError("LLM returned malformed JSON") from e


def maybe_build_client() -> LlmClient | None:
    """Return a client if the key is present; otherwise None so /ask can 503.

    We deliberately do NOT raise at startup — the rest of the app must still
    run without a Groq key.
    """
    key   = os.environ.get("GROQ_API_KEY")
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    base  = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    if not key:
        return None
    return LlmClient(api_key=key, model=model, base_url=base)
