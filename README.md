# GAM Performance Dashboard

A production-shaped Dash + FastAPI + PostgreSQL + Redis app that reports
portfolio performance, holdings, and risk against a benchmark.

The data is real (equity prices via `yfinance`), the SQL is hand-written
and uses window functions, CTEs, and a materialised view. The FastAPI
service has JSON logs with request IDs, a Redis-backed cache, and RFC
7807 problem-details error responses.

## Architecture

```
┌────────────┐   HTTP/JSON    ┌────────────────┐   asyncpg   ┌────────────┐
│ Dash :8050 │ ─────────────▶ │ FastAPI :8000  │ ──────────▶ │ Postgres   │
│ 4 pages    │                │ routers +      │             │ prices,    │
│ + Plotly   │                │ raw .sql files │             │ holdings,  │
└────────────┘                └──────┬─────────┘             │ portfolios │
                                     │ asyncio               └────────────┘
                                     ▼
                              ┌────────────┐
                              │  Redis     │   TTL cache per endpoint
                              └────────────┘

[seed] one-shot container → yfinance → Postgres (real S&P prices)
```

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:8050
- API docs (Swagger): http://localhost:8000/docs
- API health: http://localhost:8000/readyz

First start takes ~1 minute because the `seed` container downloads ~2
years of daily prices for ~30 tickers + SPY.

## Project layout

```
.
├── api/                  FastAPI service
│   ├── app/
│   │   ├── main.py       app factory + lifespan
│   │   ├── config.py     pydantic-settings
│   │   ├── logging_config.py   JSON logs, request_id ContextVar
│   │   ├── middleware.py       request-ID + access log
│   │   ├── errors.py     global exception handlers → problem+json
│   │   ├── db.py         asyncpg pool + SQL file loader
│   │   ├── cache.py      async Redis wrapper + @cached decorator
│   │   ├── deps.py       FastAPI DI providers
│   │   ├── schemas.py    Pydantic response models
│   │   ├── routers/      portfolios, holdings, performance, risk, health
│   │   └── sql/          *.sql files, grouped by domain
│   ├── Dockerfile
│   └── requirements.txt
├── dashboard/            Dash app (multi-page)
│   ├── app.py            sidebar + page router
│   ├── api_client.py     httpx client to FastAPI
│   ├── components.py     KPI card, formatters, selectors
│   ├── pages/            overview, holdings, performance, risk
│   ├── Dockerfile
│   └── requirements.txt
├── seed/                 one-shot yfinance → PG loader
│   ├── seed.py
│   ├── Dockerfile
│   └── requirements.txt
├── db/init/              SQL executed on first PG container start
│   └── 001_schema.sql
├── tests/                integration tests against the running stack
├── .github/workflows/    CI (ruff + docker compose + pytest)
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── README.md
```

## Data model

- `securities` — ticker metadata (name, sector, asset_class, currency)
- `prices` — daily OHLCV + adjusted close, PK `(ticker, as_of_date)`
- `benchmark_prices` — same shape for the benchmark (SPY)
- `portfolios` — metadata (code, strategy, benchmark, inception)
- `holdings` — weight per ticker per portfolio, time-sliced with
  `valid_from` / `valid_to` so historical positions are answerable
- `portfolio_nav` — **materialised view** computing daily NAV as
  `Σ weight × adj_close`. Refreshed at the end of the seed job.

Indexes:
- `(ticker, as_of_date DESC)` on `prices` — the main time-series pattern
- `(portfolio_id, valid_from DESC)` on `holdings` — point-in-time lookups
- Unique `(portfolio_id, as_of_date)` on `portfolio_nav` so we can
  `REFRESH MATERIALIZED VIEW CONCURRENTLY`

## Request lifecycle (single endpoint)

Example: `GET /portfolios/1/risk?window_days=180`

1. Starlette middleware (`RequestContextMiddleware`) generates a
   `request_id` (uuid4 unless the caller supplied `X-Request-ID`) and
   stores it in a `ContextVar`.
2. The route handler resolves the asyncpg pool and Cache instance via
   FastAPI dependencies.
3. The inner function is decorated with `@cached("risk.metrics", ttl=600)`.
   The decorator builds a cache key from the call args, checks Redis, and
   either returns the cached JSON or falls through to the query.
4. The SQL is loaded once from `app/sql/risk/risk_metrics.sql` (cached
   in-memory after the first load) and executed with positional params.
5. Result is serialised via the `RiskMetrics` Pydantic model; JSON body
   is returned with `X-Request-ID` header echoed back.
6. Middleware emits one JSON access-log line with method, path, status,
   and elapsed_ms.

## SQL highlights (what to talk about in interview)

**KPI summary (`portfolios/kpi_summary.sql`)** — uses `LAG()` for
same-day return and correlated scalar subqueries with `date_trunc` to
find the month-end and year-end NAV anchors in a single pass.

**Cumulative returns vs. benchmark (`performance/cum_returns_vs_bench.sql`)**
— joins portfolio NAV to benchmark prices on `as_of_date`, then uses
`FIRST_VALUE(...) OVER (ORDER BY as_of_date)` to rebase both series to
zero on the first observed date.

**Rolling metrics (`performance/rolling_metrics.sql`)** — computes
`STDDEV_SAMP` and `AVG` in a windowed frame `ROWS BETWEEN N-1 PRECEDING
AND CURRENT ROW`, then annualises with `SQRT(252)`. Returns `NULL` until
the window is full (`COUNT(r) OVER w < N`).

**Risk metrics (`risk/risk_metrics.sql`)** —
- `PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY r)` for historical VaR.
- `COVAR_POP(p, b) / VAR_POP(b)` for portfolio beta vs benchmark.
- Running peak with
  `MAX(nav) OVER (ORDER BY as_of_date ROWS BETWEEN UNBOUNDED PRECEDING
  AND CURRENT ROW)` for max drawdown.

## Caching

Redis is a separate service. Keys are namespaced `gam:<endpoint>:<args>`.
Defaults to 300-second TTL; individual endpoints override
(`risk.metrics` uses 600s). If Redis is unreachable the decorator logs a
warning and returns the live DB result — the API stays up, only the
extra load goes to PG.

The NAV calculation lives in a Postgres materialised view, which is the
second caching layer: expensive aggregates (weight × price for every
day × portfolio) are precomputed rather than recomputed per request.

## Observability

Every log line is a single JSON object with `ts`, `level`, `logger`,
`message`, and `request_id`. The access-log line (emitted by
`RequestContextMiddleware`) also carries `method`, `path`, `status`,
`elapsed_ms`. In production you'd forward stdout to your log aggregator
unchanged — no parsing rules needed.

## Error model

Every error response is `application/problem+json` (RFC 7807):

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "No NAV data for portfolio 999",
  "instance": "/portfolios/999/kpis"
}
```

Validation errors include the per-field `errors` extension. Postgres
errors are logged with the SQLSTATE code and returned as a generic 500
so the raw message never leaks.

## Testing

Integration tests live in `tests/` and run against a running compose
stack. `conftest.py` probes `/readyz` up-front and skips the whole suite
if the stack isn't up, so CI output is readable.

```bash
docker compose up -d
pip install -r tests/requirements.txt
pytest -v
```

## CI

`.github/workflows/ci.yml` runs on push and PR: `ruff check`, builds the
compose stack, runs the seed, starts the API, runs `pytest`, then tears
down. API logs are dumped on failure.

## Local development without Docker

The API can run directly if you already have PG and Redis:

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_USER=gam POSTGRES_PASSWORD=gam POSTGRES_HOST=localhost \
       POSTGRES_DB=gam REDIS_HOST=localhost
uvicorn app.main:app --reload --port 8000
```

Same pattern for the dashboard (`python -m dashboard.app`).

## Tradeoffs and what I'd add next

- **Auth** — skipped for the demo. A real system would front this with
  Okta/Azure AD, JWT on the API, and per-portfolio entitlements.
- **Materialised view refresh** — today it's refreshed by the seed job.
  In prod you'd schedule this (pg_cron or an external job) after the
  end-of-day price load.
- **Back-pressure** — the asyncpg pool caps at 10. A surge past that
  queues at the pool; a production system would want structured rate
  limiting (e.g. `slowapi`) and a circuit breaker in the Dash client.
- **SQL Server / Oracle** — the target stack at RBC. The SQL uses
  standard ANSI features (`PERCENTILE_CONT`, `COVAR_POP`, window
  frames) that port directly; the `portfolio_nav` view would become
  an `INDEXED VIEW` in SQL Server or a `MATERIALIZED VIEW` in Oracle.
