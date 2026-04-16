# GAM Performance Dashboard

A production-shaped Dash + FastAPI + PostgreSQL + Redis app that reports
portfolio performance, holdings, and risk against a benchmark.

The data is real (equity prices fetched directly from Yahoo Finance's
public chart API, using `curl_cffi` to impersonate a browser's TLS
fingerprint), the SQL is hand-written and uses window functions, CTEs,
and a materialised view. The FastAPI
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

[seed] one-shot container → Yahoo chart API (via curl_cffi) → Postgres
```

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:8050
- API docs (Swagger): http://localhost:8000/docs
- API health: http://localhost:8000/readyz

First start takes ~30 seconds because the `seed` container downloads
~4 years of daily prices for 30 tickers + SPY from Yahoo's chart API.

### Note on the data source

Yahoo aggressively rate-limits `python-requests` and `httpx` user
agents. We use `curl_cffi` to impersonate a real Chrome TLS fingerprint
and call Yahoo's public chart endpoint
(`query1.finance.yahoo.com/v8/finance/chart/{ticker}`) directly — this
is the same endpoint the `yfinance` library hits internally, but going
direct avoids a compatibility bug between yfinance 0.2.x and newer
curl_cffi. If Yahoo still refuses (sustained block), the seed falls
back to deterministic synthetic prices so the stack always boots.

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
│   │   ├── deps.py       FastAPI DI providers (pool, ro_pool, cache, llm)
│   │   ├── llm.py        Groq client + prompt + response schema
│   │   ├── sqlguard.py   structural validator for LLM-emitted SQL
│   │   ├── schemas.py    Pydantic response models
│   │   ├── routers/      portfolios, holdings, performance, risk, ask, health
│   │   └── sql/          *.sql files, grouped by domain
│   ├── Dockerfile
│   └── requirements.txt
├── dashboard/            Dash app (multi-page)
│   ├── app.py            sidebar + page router
│   ├── api_client.py     httpx client to FastAPI
│   ├── components.py     KPI card, formatters, selectors
│   ├── pages/            overview, holdings, performance, risk, ask
│   ├── Dockerfile
│   └── requirements.txt
├── seed/                 one-shot Yahoo → PG loader (curl_cffi-impersonated)
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

## CI/CD

Two workflows drive everything:

- **`.github/workflows/ci.yml`** — runs on every push and PR. Executes
  on GitHub-hosted `ubuntu-latest` (NOT the self-hosted runner; this
  repo is public, and a self-hosted runner would let a malicious PR run
  code on the server). Steps: `ruff check`, build the compose stack,
  seed, start the API, run pytest, tear down.

- **`.github/workflows/cd.yml`** — runs after CI succeeds on `main`.
  Deploys to the production server over SSH:
    1. Configures an SSH key from `DEPLOY_SSH_KEY` secret.
    2. `rsync` the repo (minus `.env`, `.git`, `pgdata`, caches) into
       `/opt/dashdemo-therealsoftware/app/` on the server.
    3. Writes `/opt/dashdemo-therealsoftware/.env` on the server from
       GitHub secrets (scp'd from a tmpfile so values don't appear in
       the process table). File is chmod 600 after upload.
    4. SSHs in and runs
       `docker compose -p dashdemo --env-file .env -f app/docker-compose.prod.yml up -d --build --remove-orphans`.
    5. Polls `https://dashdemo.therealsoftware.com` until it returns
       HTTP 200, dumps server-side logs on failure.

### Production topology

```
Internet ──► Traefik (host's 80/443, Let's Encrypt) ──► dashboard :8050
                                                             │
                                                             ▼
                                                        api :8000
                                                        │         │
                                                        ▼         ▼
                                                    postgres    redis
```

Only `dashboard` joins the external `web` network (where Traefik sees
it); the rest stay on `internal`. Traefik labels on the dashboard
service route `dashdemo.therealsoftware.com` → container port 8050,
with an HTTP → HTTPS redirect middleware and Let's Encrypt cert via the
same resolver used by the main site.

### First-time setup (one-off)

1. **DNS** — add an A record for
   `dashdemo.therealsoftware.com` → `217.15.170.249`. Let's Encrypt's
   HTTP-01 challenge needs to reach the server, so if you're behind
   Cloudflare match whatever proxy setting you use for the main domain.

2. **GitHub Actions secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value |
   |---|---|
   | `DEPLOY_HOST` | `217.15.170.249` |
   | `DEPLOY_USER` | `root` |
   | `DEPLOY_SSH_KEY` | Private half of the deploy key (`~/.ssh/gam-dashdemo-deploy`). Paste the full file content. |
   | `DEPLOY_SSH_KNOWN_HOSTS` | Output of `ssh-keyscan 217.15.170.249`. |
   | `POSTGRES_PASSWORD` | Any strong value (used inside the stack only). |
   | `POSTGRES_RO_PASSWORD` | Separate strong value for the read-only role. |
   | `GROQ_API_KEY` | Your Groq API key. |

   The deploy-only SSH key is the one generated during setup and
   installed to `/root/.ssh/authorized_keys` on the server — it only
   lets us `rsync` and run `docker compose`, nothing else.

3. **Server prep** — already done:
   - `/opt/dashdemo-therealsoftware/` exists, world-readable.
   - Docker networks `web` + `internal` exist (the compose up step
     creates them if missing, but the host-shared Traefik already has
     them).

### Rollback

`docker compose` builds tag each image with the repo's current SHA, but
images aren't versioned in a registry (same pattern as the reference
site). To roll back, either:

```bash
ssh root@217.15.170.249
cd /opt/dashdemo-therealsoftware
# Option A — check out the previous SHA in app/ and re-run up -d --build
cd app && git checkout <sha> && cd ..
docker compose -p dashdemo --env-file .env -f app/docker-compose.prod.yml up -d --build
```

or click **Run workflow** on the CD action pointed at an older SHA.

### Rotating secrets

- Rotate `GROQ_API_KEY` in GitHub Secrets, then **Run workflow** on CD.
  Next deploy rewrites the server's `.env`.
- Rotate the deploy SSH key: generate a new pair, update
  `DEPLOY_SSH_KEY`, append the new public key to the server's
  `~/.ssh/authorized_keys`, then remove the old line.

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

## Natural-language query ("Ask" page)

The dashboard has a fifth page that accepts plain-English questions,
turns them into SQL via an LLM, runs the SQL, and renders the result
with an auto-picked chart type. The feature is defensive by default:
three independent layers sit between the user's text and the database.

**Pipeline**

```
 question  →  Groq (Llama 3.3 70B, OpenAI-compatible API)
           →  JSON { sql, chart_type, x_col, y_col, title, explanation }
           →  sqlguard.sanitise()   # keyword / single-stmt / LIMIT check
           →  asyncpg ro_pool       # dedicated SELECT-only role
              + SET LOCAL statement_timeout = '5s'
           →  rows + chart hints back to Dash
```

**Safety layers (defence in depth)**

1. **Prompt-level** — the system prompt gives the LLM a curated schema and
   hard-coded rules ("single SELECT, always LIMIT, never DROP"). Works
   most of the time, but an LLM is never a security boundary.
2. **Structural validation** (`api/app/sqlguard.py`) — rejects empty
   strings, multi-statement text (anything with a `;` mid-query), and
   any of `INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/GRANT/CREATE/...`.
   Appends `LIMIT 1000` if the LLM forgot one.
3. **Postgres RO role** (`db/init/002_ro_role.sql`) — the `/ask`
   endpoint uses a separate asyncpg pool that connects as `gam_ro`,
   which has `SELECT`-only grants. If both the prompt rules and the
   sanitiser were to fail, Postgres would still refuse. Per-request
   `statement_timeout = 5s` caps runaway queries.

**Configuration**

- `GROQ_API_KEY` (env only — never in source). The `/ask` endpoint
  returns 503 if unset, so the rest of the app runs fine without it.
- `GROQ_MODEL` — defaults to `llama-3.3-70b-versatile`.
- Open http://localhost:8050/ask and try: *"Top 5 holdings in the Tech
  portfolio by weight"*, or *"NAV of GAM_CORE over time"*.

**Why Groq and not Claude/OpenAI?** Groq exposes an OpenAI-compatible
endpoint and runs Llama on their LPU hardware, so responses come back
in ~1s — latency that's fine for an interactive dashboard.

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
