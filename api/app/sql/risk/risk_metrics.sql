-- Point-in-time risk metrics for a portfolio over a trailing window.
--
-- $1 = portfolio_id
-- $2 = window_days (trailing calendar days of history to use)
--
-- Metrics:
--   annualised_vol_pct    : stddev(daily_return) * sqrt(252) * 100
--   annualised_return_pct : geometric; (1+mean_r)^252 - 1
--   sharpe                : ann_return / ann_vol  (rf=0)
--   max_drawdown_pct      : running_peak vs current nav
--   var_95_pct            : 5th percentile of daily returns (historical VaR)
--   beta_vs_benchmark     : COVAR_POP(p, b) / VAR_POP(b) on aligned daily returns
WITH p_returns AS (
    SELECT
        as_of_date,
        nav,
        nav / LAG(nav) OVER (ORDER BY as_of_date) - 1 AS r
    FROM portfolio_nav
    WHERE portfolio_id = $1
      AND as_of_date >= (SELECT MAX(as_of_date) FROM portfolio_nav WHERE portfolio_id = $1)
                       - ($2::int * INTERVAL '1 day')
),
b_returns AS (
    SELECT
        bp.as_of_date,
        bp.adj_close / LAG(bp.adj_close) OVER (ORDER BY bp.as_of_date) - 1 AS r_b
    FROM benchmark_prices bp
    JOIN portfolios p ON p.benchmark = bp.benchmark
    WHERE p.portfolio_id = $1
      AND bp.as_of_date >= (SELECT MAX(as_of_date) FROM portfolio_nav WHERE portfolio_id = $1)
                          - ($2::int * INTERVAL '1 day')
),
aligned AS (
    SELECT p.as_of_date, p.r, b.r_b
    FROM p_returns p
    JOIN b_returns b USING (as_of_date)
    WHERE p.r IS NOT NULL AND b.r_b IS NOT NULL
),
drawdown AS (
    SELECT
        as_of_date,
        nav,
        MAX(nav) OVER (ORDER BY as_of_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS peak
    FROM p_returns
    WHERE nav IS NOT NULL
)
SELECT
    $1                                                                         AS portfolio_id,
    $2                                                                         AS window_days,
    (STDDEV_SAMP(r) * SQRT(252) * 100)                                         AS annualised_vol_pct,
    ((POWER(1 + AVG(r), 252) - 1) * 100)                                       AS annualised_return_pct,
    CASE WHEN STDDEV_SAMP(r) IS NULL OR STDDEV_SAMP(r) = 0 THEN 0
         ELSE ((POWER(1 + AVG(r), 252) - 1) / (STDDEV_SAMP(r) * SQRT(252))) END AS sharpe,
    (
      SELECT MIN((nav / peak - 1)) * 100 FROM drawdown
    )                                                                          AS max_drawdown_pct,
    (PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY r) * 100)                    AS var_95_pct,
    CASE WHEN VAR_POP(r_b) IS NULL OR VAR_POP(r_b) = 0 THEN 0
         ELSE (COVAR_POP(r, r_b) / VAR_POP(r_b)) END                           AS beta_vs_benchmark
FROM aligned;
