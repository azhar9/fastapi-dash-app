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
from psycopg.rows import dict_row
from tenacity import retry, stop_after_attempt, wait_exponential

# curl_cffi impersonates a real Chrome TLS fingerprint. Yahoo's query1
# endpoint blocks python-requests / httpx on sight but serves real-browser
# traffic. We go straight to the chart API (same endpoint the yfinance
# library calls internally) instead of through yfinance because the lib
# currently has a Session-object compatibility bug with curl_cffi.
try:
    from curl_cffi import requests as _curl_requests
    _BROWSER_SESSION = _curl_requests.Session(impersonate="chrome")
except Exception:  # pragma: no cover - only hit on install issues
    _BROWSER_SESSION = None

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

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

    Tiered strategy:
      1. Yahoo Finance chart API via curl_cffi. Real prices, keyless,
         adjusted close included. We rotate in a small delay between
         requests so the rate limiter stays happy.
      2. Synthetic geometric Brownian motion for anything Yahoo refused.
         Guarantees the stack always starts cleanly.

    Returns (rows, source_label) — "yfinance" / "synthetic" / "mixed".
    """
    rows: list[dict] = []
    still_missing: list[str] = list(tickers)
    used: set[str] = set()

    if _BROWSER_SESSION is not None:
        log.info("fetching %d tickers from Yahoo (direct chart API)", len(still_missing))
        fetched = []
        for i, ticker in enumerate(still_missing):
            frame = _fetch_yahoo_chart(ticker, start)
            if frame:
                rows.extend(frame)
                fetched.append(ticker)
            if i < len(still_missing) - 1:
                time.sleep(0.3)
        if fetched:
            used.add("yfinance")
            log.info("yahoo supplied %d/%d tickers", len(fetched), len(still_missing))
        still_missing = [t for t in still_missing if t not in fetched]

    if still_missing:
        log.warning("%d tickers unavailable from Yahoo, using synthetic: %s",
                    len(still_missing), still_missing)
        rows.extend(_synthetic_prices(still_missing, start).to_dict("records"))
        used.add("synthetic")

    if not used:
        return pd.DataFrame(rows), "empty"
    label = next(iter(used)) if len(used) == 1 else "mixed(" + "+".join(sorted(used)) + ")"
    return pd.DataFrame(rows), label


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
def _fetch_yahoo_chart(ticker: str, start: str) -> list[dict] | None:
    """Hit Yahoo's chart API directly, parse the JSON, return row dicts.

    Response shape:
        { "chart": { "result": [ {
            "timestamp": [unix_ts, ...],
            "indicators": { "quote": [{ "open":[], "high":[],
                                        "low":[], "close":[], "volume":[] }],
                            "adjclose": [{ "adjclose": [] }] }
        } ] } }
    """
    start_ts = int(time.mktime(date.fromisoformat(start).timetuple()))
    end_ts   = int(time.time()) + 86400
    url = YAHOO_CHART_URL.format(ticker=ticker)
    params = {"period1": start_ts, "period2": end_ts, "interval": "1d"}
    try:
        resp = _BROWSER_SESSION.get(url, params=params, timeout=15)
    except Exception as e:
        log.warning("yahoo request failed for %s: %s", ticker, e)
        return None
    if resp.status_code != 200:
        log.warning("yahoo %s for %s (body: %s)", resp.status_code, ticker, resp.text[:120])
        return None
    try:
        payload = resp.json()
        result  = payload["chart"]["result"][0]
        ts      = result["timestamp"]
        quote   = result["indicators"]["quote"][0]
        adj     = result["indicators"].get("adjclose", [{}])[0].get("adjclose") or quote["close"]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        log.warning("yahoo parse failed for %s: %s", ticker, e)
        return None

    out: list[dict] = []
    for i, t in enumerate(ts):
        close = quote["close"][i]
        if close is None:
            continue
        d = date.fromtimestamp(t)
        out.append({
            "ticker":     ticker,
            "as_of_date": d,
            "open":       _maybe_float(quote["open"][i]),
            "high":       _maybe_float(quote["high"][i]),
            "low":        _maybe_float(quote["low"][i]),
            "close":      float(close),
            "adj_close":  float(adj[i]) if adj[i] is not None else float(close),
            "volume":     int(quote["volume"][i]) if quote["volume"][i] is not None else None,
        })
    return out


def _maybe_float(v) -> float | None:
    return float(v) if v is not None else None


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

    if _BROWSER_SESSION is not None:
        rows = _fetch_yahoo_chart(ticker, start)
        if rows:
            df = pd.DataFrame(rows)[["as_of_date", "close", "adj_close"]]
            df["benchmark"] = ticker
            log.info("benchmark source: yfinance (%d rows)", len(df))
            return df[["benchmark", "as_of_date", "close", "adj_close"]]

    log.warning("benchmark %s unavailable from Yahoo, using synthetic", ticker)
    syn = _synthetic_prices([ticker], start)
    out = syn[["as_of_date", "close", "adj_close"]].copy()
    out["benchmark"] = ticker
    return out[["benchmark", "as_of_date", "close", "adj_close"]]


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
