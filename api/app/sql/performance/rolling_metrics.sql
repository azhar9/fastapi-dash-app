-- Rolling annualised vol and rolling Sharpe over a trailing window.
--
-- $1 = portfolio_id
-- $2 = window_days  (e.g. 30, 60, 90)
--
-- STDDEV_SAMP and AVG over a ROWS BETWEEN N PRECEDING AND CURRENT ROW window
-- give us per-day rolling metrics. We annualise using sqrt(252)/252 trading days.
-- Risk-free rate is assumed zero for the demo (common simplification in
-- performance reporting when the rate is small).
WITH returns AS (
    SELECT
        as_of_date,
        nav,
        nav / LAG(nav) OVER (ORDER BY as_of_date) - 1 AS r
    FROM portfolio_nav
    WHERE portfolio_id = $1
),
rolling AS (
    SELECT
        as_of_date,
        STDDEV_SAMP(r) OVER w AS sd,
        AVG(r)         OVER w AS mean_r,
        COUNT(r)       OVER w AS n_obs
    FROM returns
    WINDOW w AS (
        ORDER BY as_of_date
        ROWS BETWEEN ($2::int - 1) PRECEDING AND CURRENT ROW
    )
)
SELECT
    as_of_date,
    CASE WHEN n_obs < $2 OR sd IS NULL
         THEN NULL
         ELSE (sd * SQRT(252) * 100)::float END AS rolling_vol_pct,
    CASE WHEN n_obs < $2 OR sd IS NULL OR sd = 0
         THEN NULL
         ELSE ((mean_r * 252) / (sd * SQRT(252)))::float END AS rolling_sharpe
FROM rolling
ORDER BY as_of_date;
