# Portfolio Analytics — a FastAPI + Dash + AI learning project

A small end-to-end project I'm using to learn how FastAPI, Dash,
PostgreSQL, Redis, and LLM-backed natural-language query interfaces fit
together. The app is a portfolio-analytics dashboard: it fetches real
daily equity prices, builds three demo portfolios, and shows NAV,
holdings, returns, and risk metrics — plus an "Ask" page where you can
type a question in plain English and the backend generates SQL via an
LLM, validates it, and runs it.

It's deliberately scoped small, but each piece is production-shaped:
structured JSON logging, RFC 7807 error responses, a Redis cache layer,
hand-written SQL with window functions and a materialised view, pytest
integration tests, and GitHub Actions CI/CD that deploys to a
Traefik-fronted server.

## Architecture

```
┌────────────┐   HTTP/JSON    ┌────────────────┐   asyncpg   ┌────────────┐
│ Dash :8050 │ ─────────────▶ │ FastAPI :8000  │ ──────────▶ │ Postgres   │
│ 5 pages    │                │ routers +      │             │ prices,    │
│ + Plotly   │                │ raw .sql files │             │ holdings,  │
└────────────┘                └──────┬─────────┘             │ portfolios │
                                     │ asyncio               └────────────┘
                                     ▼
                              ┌────────────┐
                              │  Redis     │   TTL cache per endpoint
                              └────────────┘

                              ┌──────────────┐
                              │  Groq LLM    │   /ask page only
                              └──────────────┘

[seed] one-shot container → Yahoo chart API (via curl_cffi) → Postgres
```

## What's in here

- **Four read-only analytics pages**: portfolio overview, holdings,
  performance vs. benchmark, risk metrics.
- **An "Ask" page**: type a question, the backend calls a Groq-hosted
  Llama model, gets back a SQL query in strict JSON, validates it,
  runs it against a read-only Postgres role, and renders the result
  as a table plus an auto-chosen chart (line / bar / pie).
- **Hand-written SQL** with `LAG`, `FIRST_VALUE`, rolling
  `STDDEV_SAMP`/`AVG` window frames, `PERCENTILE_CONT` (VaR),
  `COVAR_POP/VAR_POP` (beta), running peak for drawdown.
- **A materialised view** (`portfolio_nav`) that pre-computes daily
  weighted NAV so the performance queries don't aggregate prices per
  request.
- **Three safety layers** in front of LLM-generated SQL: prompt rules,
  a structural validator, and a PG role that only has SELECT grants.

## Quick start

```bash
cp .env.example .env           # defaults are fine for local dev
docker compose up --build
```

- Dashboard: http://localhost:8050
- API docs (Swagger): http://localhost:8088/docs
- Ask page: http://localhost:8050/ask

The `/ask` endpoint returns 503 unless `GROQ_API_KEY` is set in `.env`;
the rest of the app runs fine without it.

First start takes ~30 seconds — the `seed` container pulls ~4 years of
daily prices for ~30 tickers + SPY from Yahoo's chart API.

### Note on the data source

Yahoo rate-limits `python-requests` / `httpx` user agents aggressively,
and the `yfinance` library has a compatibility bug with current
`curl_cffi` sessions. To get real data reliably, the seed calls Yahoo's
public chart endpoint
(`query1.finance.yahoo.com/v8/finance/chart/{ticker}`) directly, using
a `curl_cffi` session that impersonates Chrome's TLS fingerprint. If
Yahoo still blocks (sustained rate limit), the seed falls back to
deterministic geometric-Brownian-motion synthetic prices so the stack
always boots.

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
├── seed/                 one-shot Yahoo → PG loader
├── db/init/              SQL executed on first PG container start
├── tests/                integration tests against the running stack
├── .github/workflows/    CI + CD
├── docker-compose.yml        local dev stack
├── docker-compose.prod.yml   production stack (Traefik-labelled)
├── pyproject.toml
└── .env.example
```

## Data model

- `securities` — ticker metadata (name, sector, asset_class, currency)
- `prices` — daily OHLCV + adjusted close, PK `(ticker, as_of_date)`
- `benchmark_prices` — same shape for the benchmark (SPY)
- `portfolios` — three demo portfolios with codes `CORE`, `TECH`,
  `DIVIDEND`
- `holdings` — weight per ticker per portfolio, time-sliced with
  `valid_from` / `valid_to` so historical positions are answerable
- `portfolio_nav` — **materialised view** computing daily NAV as
  `Σ weight × adj_close`. Refreshed at the end of the seed job.

Indexes:
- `(ticker, as_of_date DESC)` on `prices` — main time-series pattern
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
   The decorator builds a cache key from the call args, checks Redis,
   and either returns the cached JSON or falls through to the query.
4. The SQL is loaded once from `app/sql/risk/risk_metrics.sql` (cached
   in-memory after the first load) and executed with positional params.
5. Result is serialised via the `RiskMetrics` Pydantic model; JSON body
   is returned with `X-Request-ID` header echoed back.
6. Middleware emits one JSON access-log line with method, path, status,
   and elapsed_ms.

## SQL highlights

**KPI summary (`portfolios/kpi_summary.sql`)** — uses `LAG()` for
same-day return and correlated scalar subqueries with `date_trunc` to
find the month-end and year-end NAV anchors in a single pass.

**Cumulative returns vs. benchmark (`performance/cum_returns_vs_bench.sql`)**
— joins portfolio NAV to benchmark prices on `as_of_date`, then uses
`FIRST_VALUE(...) OVER (ORDER BY as_of_date)` to rebase both series to
zero on the first observed date.

**Rolling metrics (`performance/rolling_metrics.sql`)** — computes
`STDDEV_SAMP` and `AVG` in a windowed frame `ROWS BETWEEN N-1 PRECEDING
AND CURRENT ROW`, then annualises with `SQRT(252)`. Returns `NULL`
until the window is full (`COUNT(r) OVER w < N`).

**Risk metrics (`risk/risk_metrics.sql`)** —
- `PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY r)` for historical VaR.
- `COVAR_POP(p, b) / VAR_POP(b)` for portfolio beta vs benchmark.
- Running peak with
  `MAX(nav) OVER (ORDER BY as_of_date ROWS BETWEEN UNBOUNDED PRECEDING
  AND CURRENT ROW)` for max drawdown.

## Caching

Redis is a separate service. Keys are namespaced
`portfolio:<endpoint>:<args>`. Default TTL is 300s; individual
endpoints override (`risk.metrics` uses 600s). If Redis is unreachable
the decorator logs a warning and falls through to the DB — the API
stays up, only the extra load goes to PG.

The NAV calculation lives in a Postgres materialised view, which is
the second caching layer: expensive aggregates (weight × price for
every day × portfolio) are precomputed rather than recomputed per
request.

## Observability

Every log line is a single JSON object with `ts`, `level`, `logger`,
`message`, and `request_id`. The access-log line (emitted by
`RequestContextMiddleware`) also carries `method`, `path`, `status`,
`elapsed_ms`. In production you'd forward stdout to your log
aggregator unchanged — no parsing rules needed.

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

## Natural-language query ("Ask" page)

The dashboard has a fifth page that accepts plain-English questions,
turns them into SQL via an LLM, runs the SQL, and renders the result
with an auto-picked chart type. It's defensive by default: three
independent layers sit between the user's text and the database.

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

1. **Prompt-level** — the system prompt gives the LLM a curated schema
   and hard-coded rules ("single SELECT, always LIMIT, never DROP").
   Works most of the time, but an LLM is never a security boundary.
2. **Structural validation** (`api/app/sqlguard.py`) — rejects empty
   strings, multi-statement text (anything with a `;` mid-query), and
   any of `INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/GRANT/CREATE/...`.
   Appends `LIMIT 1000` if the LLM forgot one.
3. **Postgres RO role** (`db/init/002_ro_role.sql`) — the `/ask`
   endpoint uses a separate asyncpg pool that connects as `app_ro`,
   which has `SELECT`-only grants. If both the prompt rules and the
   sanitiser were to fail, Postgres would still refuse. Per-request
   `statement_timeout = 5s` caps runaway queries.

**Configuration**

- `GROQ_API_KEY` (env only — never in source). The `/ask` endpoint
  returns 503 if unset, so the rest of the app runs fine without it.
- `GROQ_MODEL` — defaults to `llama-3.3-70b-versatile`.
- Try: *"Top 5 holdings in the Tech portfolio by weight"*, or
  *"NAV of the Core portfolio over time"*.

**Why Groq?** Groq exposes an OpenAI-compatible endpoint and runs
Llama on their LPU hardware, so responses come back in ~1s — fine for
an interactive dashboard.

## Testing

Integration tests live in `tests/` and run against a running compose
stack. `conftest.py` probes `/readyz` up-front and skips the whole
suite if the stack isn't up, so CI output stays readable.

```bash
docker compose up -d
pip install -r tests/requirements.txt
pytest -v
```

There's also a unit-test module for `sqlguard` that doesn't need any
infrastructure.

## CI/CD

Two workflows:

- **`.github/workflows/ci.yml`** — runs on every push and PR, on
  GitHub-hosted `ubuntu-latest` (not a self-hosted runner, because
  this repo is public). Steps: `ruff check`, build the compose stack,
  seed, start the API, run pytest, tear down.

- **`.github/workflows/cd.yml`** — runs after CI succeeds on `main`.
  Deploys to the demo server over SSH:
    1. Configures an SSH key from the `DEPLOY_SSH_KEY` secret.
    2. `rsync` the repo (minus `.env`, `.git`, `pgdata`, caches) into
       `/opt/dashdemo-therealsoftware/app/` on the server.
    3. Writes `/opt/dashdemo-therealsoftware/.env` on the server from
       GitHub secrets (scp'd from a tmpfile so values don't appear in
       the process table, chmod 600 after upload).
    4. SSHs in and runs
       `docker compose -p dashdemo --env-file .env -f app/docker-compose.prod.yml up -d --build --remove-orphans`.
    5. Polls the public URL until it returns HTTP 200, dumps
       server-side logs on failure.

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
service route the demo subdomain → container port 8050, with an
HTTP → HTTPS redirect and Let's Encrypt cert via the host's resolver.

### First-time setup (one-off)

1. **DNS** — add an A record for the demo subdomain pointing at the
   server. Let's Encrypt's HTTP-01 challenge needs to reach the
   server, so match whatever proxy setting the rest of the zone uses.

2. **GitHub Actions secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value |
   |---|---|
   | `DEPLOY_HOST` | Server IP |
   | `DEPLOY_USER` | SSH user (e.g. `root`) |
   | `DEPLOY_SSH_KEY` | Private half of a deploy-only SSH key |
   | `DEPLOY_SSH_KNOWN_HOSTS` | Output of `ssh-keyscan <host>` |
   | `POSTGRES_PASSWORD` | Any strong value |
   | `POSTGRES_RO_PASSWORD` | Separate strong value |
   | `GROQ_API_KEY` | Your Groq API key |

   The deploy-only SSH key's public half lives in the server's
   `~/.ssh/authorized_keys` — it only lets CI `rsync` and run
   `docker compose`.

### Rollback

```bash
ssh <deploy_user>@<deploy_host>
cd /opt/dashdemo-therealsoftware
cd app && git checkout <sha> && cd ..
docker compose -p dashdemo --env-file .env -f app/docker-compose.prod.yml up -d --build
```

or re-run the CD workflow pointed at an older SHA via **Run workflow**.

### Rotating secrets

- Rotate `GROQ_API_KEY` in GitHub Secrets, then **Run workflow** on
  CD. The next deploy rewrites the server's `.env`.
- Rotate the deploy SSH key: generate a new pair, update
  `DEPLOY_SSH_KEY`, append the new public key to the server's
  `~/.ssh/authorized_keys`, then remove the old line.

## Local development without Docker

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_USER=app POSTGRES_PASSWORD=app POSTGRES_HOST=localhost \
       POSTGRES_DB=portfolio REDIS_HOST=localhost
uvicorn app.main:app --reload --port 8000
```

Same pattern for the dashboard (`python -m dashboard.app`).

## What I'd add next

- **Auth** — skipped for the demo. A real system would sit behind
  Okta/Azure AD and have per-portfolio entitlements.
- **Scheduled matview refresh** — today it's refreshed by the seed
  job. In prod you'd schedule this (pg_cron or an external job) after
  the end-of-day price load.
- **Rate limiting on `/ask`** — the LLM call is cheap and fast on
  Groq, but a real deploy would rate-limit per IP and cache identical
  questions.
