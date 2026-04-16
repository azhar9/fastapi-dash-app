"""Populate Postgres with real market data and synthetic portfolios.

Runs once at stack start. Idempotent: re-running is safe, it uses
INSERT ... ON CONFLICT DO NOTHING for prices and TRUNCATE+INSERT for
the lookup tables (portfolios/holdings/securities) which are small.
"""
from __future__ import annotations

import logging
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import psycopg
import yfinance as yf
from psycopg.rows import dict_row
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s seed %(message)s",
)
log = logging.getLogger("seed")


# A small sector map lets us show a sector-breakdown chart without another
# API call. Keeping it inline (not a CSV) keeps the seed container simple.
SECTOR_MAP: dict[str, tuple[str, str]] = {
    "AAPL":  ("Apple Inc.",                    "Technology"),
    "MSFT":  ("Microsoft Corp.",               "Technology"),
    "GOOGL": ("Alphabet Inc. Class A",         "Communication Services"),
    "AMZN":  ("Amazon.com Inc.",               "Consumer Discretionary"),
    "NVDA":  ("NVIDIA Corp.",                  "Technology"),
    "META":  ("Meta Platforms Inc.",           "Communication Services"),
    "TSLA":  ("Tesla Inc.",                    "Consumer Discretionary"),
    "BRK-B": ("Berkshire Hathaway Inc. B",     "Financials"),
    "JPM":   ("JPMorgan Chase & Co.",          "Financials"),
    "V":     ("Visa Inc.",                     "Financials"),
    "JNJ":   ("Johnson & Johnson",             "Health Care"),
    "WMT":   ("Walmart Inc.",                  "Consumer Staples"),
    "PG":    ("Procter & Gamble Co.",          "Consumer Staples"),
    "XOM":   ("Exxon Mobil Corp.",             "Energy"),
    "UNH":   ("UnitedHealth Group Inc.",       "Health Care"),
    "HD":    ("Home Depot Inc.",               "Consumer Discretionary"),
    "MA":    ("Mastercard Inc.",               "Financials"),
    "BAC":   ("Bank of America Corp.",         "Financials"),
    "PFE":   ("Pfizer Inc.",                   "Health Care"),
    "KO":    ("Coca-Cola Co.",                 "Consumer Staples"),
    "PEP":   ("PepsiCo Inc.",                  "Consumer Staples"),
    "CVX":   ("Chevron Corp.",                 "Energy"),
    "MRK":   ("Merck & Co.",                   "Health Care"),
    "ABBV":  ("AbbVie Inc.",                   "Health Care"),
    "CSCO":  ("Cisco Systems Inc.",            "Technology"),
    "TMO":   ("Thermo Fisher Scientific Inc.", "Health Care"),
    "ORCL":  ("Oracle Corp.",                  "Technology"),
    "ADBE":  ("Adobe Inc.",                    "Technology"),
    "CRM":   ("Salesforce Inc.",               "Technology"),
    "NFLX":  ("Netflix Inc.",                  "Communication Services"),
}


@dataclass
class Env:
    dsn: str
    tickers: list[str]
    benchmark: str
    start_date: str


def load_env() -> Env:
    user = os.environ["POSTGRES_USER"]
    pwd  = os.environ["POSTGRES_PASSWORD"]
    host = os.environ["POSTGRES_HOST"]
    port = os.environ.get("POSTGRES_PORT", "5432")
    db   = os.environ["POSTGRES_DB"]
    tickers_raw = os.environ.get("SEED_TICKERS") or ",".join(SECTOR_MAP.keys())
    return Env(
        dsn=f"postgresql://{user}:{pwd}@{host}:{port}/{db}",
        tickers=[t.strip() for t in tickers_raw.split(",") if t.strip()],
        benchmark=os.environ.get("SEED_BENCHMARK", "SPY"),
        start_date=os.environ.get("SEED_START_DATE", "2022-01-01"),
    )


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, max=30))
def connect(dsn: str) -> psycopg.Connection:
    # Postgres may still be starting when this container launches.
    # Retry with exponential backoff rather than sleeping blindly.
    return psycopg.connect(dsn, row_factory=dict_row)


def already_seeded(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM prices")
        row = cur.fetchone()
        return bool(row and row["n"] > 0)


def download_prices(tickers: list[str], start: str) -> tuple[pd.DataFrame, str]:
    """Fetch daily prices for every ticker.

    Strategy:
      1. Try yfinance one ticker at a time with a small delay between calls.
         Batch downloads get rate-limited almost immediately in 2025-2026.
      2. If *every* ticker fails (e.g. sustained YFRateLimitError), fall back
         to a deterministic synthetic price series so the demo stack still
         starts. The caller is told which path we took.
    """
    rows: list[dict] = []
    failed: list[str] = []
    for i, ticker in enumerate(tickers):
        frame = _fetch_one_yfinance(ticker, start)
        if frame is None or frame.empty:
            failed.append(ticker)
            continue
        rows.extend(_normalise_yf_rows(ticker, frame))
        # Courtesy delay so Yahoo's rate limiter doesn't escalate.
        if i < len(tickers) - 1:
            time.sleep(0.6)

    if not rows:
        log.warning(
            "yfinance unavailable for all %d tickers; falling back to synthetic prices",
            len(tickers),
        )
        return _synthetic_prices(tickers, start), "synthetic"

    if failed:
        log.warning("yfinance failed for %d/%d tickers, filling with synthetic: %s",
                    len(failed), len(tickers), failed)
        rows.extend(_synthetic_prices(failed, start).to_dict("records"))
        return pd.DataFrame(rows), "mixed"

    return pd.DataFrame(rows), "yfinance"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
def _fetch_one_yfinance(ticker: str, start: str) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(ticker).history(start=start, auto_adjust=False)
    except Exception as e:
        log.warning("yfinance error for %s: %s", ticker, e)
        return None
    if df is None or df.empty:
        return None
    return df.reset_index()


def _normalise_yf_rows(ticker: str, sub: pd.DataFrame) -> list[dict]:
    sub = sub.rename(columns={
        "Date": "dt", "Open": "o", "High": "h", "Low": "l",
        "Close": "c", "Adj Close": "ac", "Volume": "v",
    })
    if "ac" not in sub.columns:
        sub["ac"] = sub["c"]
    out = []
    for r in sub.itertuples(index=False):
        out.append({
            "ticker": ticker,
            "as_of_date": r.dt.date() if hasattr(r.dt, "date") else r.dt,
            "open":      float(r.o)  if pd.notna(r.o)  else None,
            "high":      float(r.h)  if pd.notna(r.h)  else None,
            "low":       float(r.l)  if pd.notna(r.l)  else None,
            "close":     float(r.c),
            "adj_close": float(r.ac),
            "volume":    int(r.v)    if pd.notna(r.v)  else None,
        })
    return out


def _synthetic_prices(tickers: list[str], start: str) -> pd.DataFrame:
    """Deterministic geometric-Brownian-motion prices.

    Gives a realistic-looking price series per ticker, reproducible because
    the RNG is seeded from the ticker name. Weekends are skipped.
    """
    start_dt = date.fromisoformat(start)
    end_dt   = date.today()
    dates: list[date] = []
    d = start_dt
    while d <= end_dt:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)

    rows: list[dict] = []
    for ticker in tickers:
        rng = random.Random(ticker)
        price = 50 + rng.random() * 150          # starting price 50–200
        mu    = 0.08 / 252                        # ~8% annual drift
        sigma = 0.20 / math.sqrt(252)             # ~20% annual vol
        for d in dates:
            shock = rng.gauss(mu, sigma)
            price = max(1.0, price * (1 + shock))
            rows.append({
                "ticker":     ticker,
                "as_of_date": d,
                "open":       round(price * (1 + rng.uniform(-0.005, 0.005)), 4),
                "high":       round(price * (1 + rng.uniform(0.0, 0.01)), 4),
                "low":        round(price * (1 + rng.uniform(-0.01, 0.0)), 4),
                "close":      round(price, 4),
                "adj_close":  round(price, 4),
                "volume":     rng.randint(1_000_000, 20_000_000),
            })
    return pd.DataFrame(rows)


def download_benchmark(ticker: str, start: str) -> pd.DataFrame:
    log.info("downloading benchmark %s", ticker)
    df = _fetch_one_yfinance(ticker, start)
    if df is None or df.empty:
        log.warning("yfinance failed for benchmark %s, using synthetic", ticker)
        syn = _synthetic_prices([ticker], start)
        out = syn[["as_of_date", "close", "adj_close"]].copy()
        out["benchmark"] = ticker
        return out[["benchmark", "as_of_date", "close", "adj_close"]]
    df = df.rename(columns={"Adj Close": "adj_close", "Close": "close", "Date": "as_of_date"})
    df["benchmark"] = ticker
    if "adj_close" not in df.columns:
        df["adj_close"] = df["close"]
    return df[["benchmark", "as_of_date", "close", "adj_close"]]


def insert_securities(conn: psycopg.Connection, tickers: list[str]) -> None:
    rows = []
    for t in tickers:
        name, sector = SECTOR_MAP.get(t, (t, "Unknown"))
        rows.append((t, name, sector))
    with conn.cursor() as cur:
        cur.execute("TRUNCATE securities CASCADE")
        cur.executemany(
            "INSERT INTO securities (ticker, name, sector) VALUES (%s, %s, %s)",
            rows,
        )


def insert_prices(conn: psycopg.Connection, df: pd.DataFrame) -> None:
    if df.empty:
        return
    records = df.to_records(index=False)
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO prices (ticker, as_of_date, open, high, low, close, adj_close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, as_of_date) DO NOTHING
            """,
            [tuple(r) for r in records],
        )
    log.info("inserted %d price rows", len(df))


def insert_benchmark_prices(conn: psycopg.Connection, df: pd.DataFrame) -> None:
    if df.empty:
        return
    records = [
        (r.benchmark, r.as_of_date.date() if hasattr(r.as_of_date, "date") else r.as_of_date,
         float(r.close), float(r.adj_close))
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO benchmark_prices (benchmark, as_of_date, close, adj_close)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (benchmark, as_of_date) DO NOTHING
            """,
            records,
        )
    log.info("inserted %d benchmark rows", len(df))


def build_portfolios(conn: psycopg.Connection, tickers: list[str], benchmark: str, start: str) -> None:
    # Three demo portfolios so the dashboard has something to switch between.
    # Weights are drawn from a fixed seed to keep runs reproducible.
    rng = random.Random(42)

    portfolios = [
        ("GAM_CORE",   "GAM Core Equity",       "Core Equity (diversified large-cap)"),
        ("GAM_TECH",   "GAM Tech Overweight",   "Technology-tilted growth"),
        ("GAM_DIVIDEND", "GAM Dividend Focus",  "Dividend-paying blue chips"),
    ]

    with conn.cursor() as cur:
        cur.execute("TRUNCATE portfolios, holdings RESTART IDENTITY CASCADE")
        for code, name, strategy in portfolios:
            cur.execute(
                """
                INSERT INTO portfolios (code, name, strategy, benchmark, inception, base_ccy)
                VALUES (%s, %s, %s, %s, %s, 'USD')
                RETURNING portfolio_id
                """,
                (code, name, strategy, benchmark, date.fromisoformat(start)),
            )
            pid = cur.fetchone()["portfolio_id"]
            universe = _pick_universe(code, tickers, rng)
            weights = _draw_weights(universe, rng)
            for ticker, w in weights.items():
                cur.execute(
                    """
                    INSERT INTO holdings (portfolio_id, ticker, weight, valid_from, valid_to)
                    VALUES (%s, %s, %s, %s, NULL)
                    """,
                    (pid, ticker, w, date.fromisoformat(start)),
                )
    log.info("built %d portfolios", len(portfolios))


def _pick_universe(code: str, all_tickers: list[str], rng: random.Random) -> list[str]:
    if code == "GAM_TECH":
        tech = [t for t in all_tickers if SECTOR_MAP.get(t, (None, None))[1] == "Technology"]
        others = [t for t in all_tickers if t not in tech]
        rng.shuffle(others)
        return tech + others[:3]
    if code == "GAM_DIVIDEND":
        dividend_like = ["JNJ", "PG", "KO", "PEP", "XOM", "CVX", "MRK", "ABBV", "WMT", "JPM", "V", "MA"]
        return [t for t in dividend_like if t in all_tickers]
    # Core — 15 names across sectors
    pool = list(all_tickers)
    rng.shuffle(pool)
    return pool[:15]


def _draw_weights(universe: list[str], rng: random.Random) -> dict[str, float]:
    raw = [rng.uniform(0.3, 1.0) for _ in universe]
    total = sum(raw)
    return {t: round(w / total, 6) for t, w in zip(universe, raw, strict=False)}


def refresh_nav(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY portfolio_nav")
    log.info("refreshed portfolio_nav matview")


def main() -> int:
    env = load_env()
    log.info("connecting to %s", env.dsn.split("@")[-1])
    with connect(env.dsn) as conn:
        conn.autocommit = False
        if already_seeded(conn):
            log.info("prices already present — skipping download, refreshing matview only")
            try:
                refresh_nav(conn)
                conn.commit()
            except psycopg.Error:
                # CONCURRENTLY requires at least one prior non-concurrent refresh.
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute("REFRESH MATERIALIZED VIEW portfolio_nav")
                conn.commit()
            return 0

        insert_securities(conn, env.tickers)
        prices, source = download_prices(env.tickers, env.start_date)
        log.info("price data source: %s", source)
        insert_prices(conn, prices)
        bench = download_benchmark(env.benchmark, env.start_date)
        insert_benchmark_prices(conn, bench)
        build_portfolios(conn, env.tickers, env.benchmark, env.start_date)
        conn.commit()

        # First refresh must be non-concurrent to populate the matview.
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW portfolio_nav")
        conn.commit()
        log.info("seed complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
