-- Schema for the portfolio-performance demo.
-- Executed by the official postgres image on first container start
-- (files in /docker-entrypoint-initdb.d run once, on an empty data dir).

CREATE TABLE IF NOT EXISTS securities (
    ticker        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    sector        TEXT NOT NULL,
    asset_class   TEXT NOT NULL DEFAULT 'Equity',
    currency      CHAR(3) NOT NULL DEFAULT 'USD'
);

CREATE TABLE IF NOT EXISTS prices (
    ticker      TEXT NOT NULL REFERENCES securities(ticker) ON DELETE CASCADE,
    as_of_date  DATE NOT NULL,
    open        NUMERIC(18, 6),
    high        NUMERIC(18, 6),
    low         NUMERIC(18, 6),
    close       NUMERIC(18, 6) NOT NULL,
    adj_close   NUMERIC(18, 6) NOT NULL,
    volume      BIGINT,
    PRIMARY KEY (ticker, as_of_date)
);

-- Query pattern is "latest price for ticker" and "price series over date range",
-- so a descending index on date pays off more than the PK alone.
CREATE INDEX IF NOT EXISTS idx_prices_date       ON prices (as_of_date);
CREATE INDEX IF NOT EXISTS idx_prices_ticker_dt  ON prices (ticker, as_of_date DESC);

-- Benchmark prices live in the same shape as equity prices but stay separate
-- so that queries against "the universe" don't need a flag filter.
CREATE TABLE IF NOT EXISTS benchmark_prices (
    benchmark   TEXT NOT NULL,
    as_of_date  DATE NOT NULL,
    close       NUMERIC(18, 6) NOT NULL,
    adj_close   NUMERIC(18, 6) NOT NULL,
    PRIMARY KEY (benchmark, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_bench_date ON benchmark_prices (as_of_date);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id  SERIAL PRIMARY KEY,
    code          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    strategy      TEXT NOT NULL,
    benchmark     TEXT NOT NULL,
    inception     DATE NOT NULL,
    base_ccy      CHAR(3) NOT NULL DEFAULT 'USD'
);

-- Holdings are time-sliced (valid_from / valid_to) so we can answer
-- "what did the portfolio look like on date X" without rebuilding history.
-- valid_to NULL means "current".
CREATE TABLE IF NOT EXISTS holdings (
    portfolio_id  INT  NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    ticker        TEXT NOT NULL REFERENCES securities(ticker) ON DELETE CASCADE,
    weight        NUMERIC(8, 6) NOT NULL CHECK (weight >= 0),
    valid_from    DATE NOT NULL,
    valid_to      DATE,
    PRIMARY KEY (portfolio_id, ticker, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_holdings_portfolio ON holdings (portfolio_id, valid_from DESC);

-- Materialised view of daily portfolio NAV.
-- Refreshed by the seed job after prices are loaded, and again whenever
-- holdings change. For a prod system you'd refresh on a schedule or
-- trigger; for the demo we refresh at the end of the seed.
CREATE MATERIALIZED VIEW IF NOT EXISTS portfolio_nav AS
WITH active_holdings AS (
    SELECT
        h.portfolio_id,
        h.ticker,
        h.weight,
        h.valid_from,
        COALESCE(h.valid_to, DATE '9999-12-31') AS valid_to
    FROM holdings h
),
weighted AS (
    SELECT
        ah.portfolio_id,
        p.as_of_date,
        SUM(ah.weight * p.adj_close) AS weighted_close
    FROM active_holdings ah
    JOIN prices p
      ON p.ticker = ah.ticker
     AND p.as_of_date >= ah.valid_from
     AND p.as_of_date <  ah.valid_to
    GROUP BY ah.portfolio_id, p.as_of_date
)
SELECT
    portfolio_id,
    as_of_date,
    weighted_close AS nav
FROM weighted;

CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_nav_pk
    ON portfolio_nav (portfolio_id, as_of_date);
