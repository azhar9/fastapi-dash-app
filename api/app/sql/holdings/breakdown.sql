-- Current holdings for a portfolio with latest price and market value.
-- $1 = portfolio_id
WITH latest_prices AS (
    SELECT DISTINCT ON (ticker)
        ticker,
        as_of_date,
        adj_close
    FROM prices
    ORDER BY ticker, as_of_date DESC
),
current_holdings AS (
    SELECT
        h.portfolio_id,
        h.ticker,
        h.weight
    FROM holdings h
    WHERE h.portfolio_id = $1
      AND h.valid_to IS NULL
)
SELECT
    s.ticker,
    s.name,
    s.sector,
    (ch.weight * 100)::float                    AS weight_pct,
    lp.adj_close::float                         AS price,
    (ch.weight * lp.adj_close * 1000000)::float AS market_value
FROM current_holdings ch
JOIN securities     s  ON s.ticker  = ch.ticker
JOIN latest_prices  lp ON lp.ticker = ch.ticker
ORDER BY ch.weight DESC;
