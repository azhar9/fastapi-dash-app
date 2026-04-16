-- Cumulative returns for a portfolio vs. its benchmark, rebased to 0%
-- at the first date in the requested window.
--
-- $1 = portfolio_id
-- $2 = start_date (nullable — NULL means full history from inception)
WITH p_nav AS (
    SELECT as_of_date, nav
    FROM portfolio_nav
    WHERE portfolio_id = $1
      AND ($2::date IS NULL OR as_of_date >= $2::date)
),
b AS (
    SELECT bp.as_of_date, bp.adj_close
    FROM benchmark_prices bp
    JOIN portfolios p ON p.benchmark = bp.benchmark
    WHERE p.portfolio_id = $1
      AND ($2::date IS NULL OR bp.as_of_date >= $2::date)
),
joined AS (
    -- Align on the dates that exist in both series (markets can be open for
    -- equities but not for a benchmark proxy, or vice versa).
    SELECT
        p_nav.as_of_date,
        p_nav.nav,
        b.adj_close AS bench_close
    FROM p_nav
    JOIN b USING (as_of_date)
),
rebased AS (
    SELECT
        as_of_date,
        nav         / FIRST_VALUE(nav)         OVER (ORDER BY as_of_date) - 1 AS port_cum,
        bench_close / FIRST_VALUE(bench_close) OVER (ORDER BY as_of_date) - 1 AS bench_cum
    FROM joined
)
SELECT
    as_of_date,
    (port_cum  * 100)::float AS portfolio_cum_return_pct,
    (bench_cum * 100)::float AS benchmark_cum_return_pct
FROM rebased
ORDER BY as_of_date;
