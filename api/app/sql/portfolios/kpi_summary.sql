-- Daily NAV plus same-day/MTD/YTD returns for a single portfolio.
--
-- Strategy:
--   * daily_nav      : NAV series joined with its previous-day NAV via LAG()
--   * period_anchors : for the latest date, find the NAV at (prev trading day,
--                      last trading day of prior month, last trading day of
--                      prior year) in one pass using conditional aggregation
--   * final SELECT   : turns the anchors into percentage returns.
--
-- $1 = portfolio_id
WITH daily_nav AS (
    SELECT
        portfolio_id,
        as_of_date,
        nav,
        LAG(nav) OVER (ORDER BY as_of_date) AS prev_nav
    FROM portfolio_nav
    WHERE portfolio_id = $1
),
latest AS (
    SELECT MAX(as_of_date) AS d FROM daily_nav
),
anchors AS (
    SELECT
        (SELECT nav FROM daily_nav WHERE as_of_date = (SELECT d FROM latest))                              AS nav_today,
        (SELECT prev_nav FROM daily_nav WHERE as_of_date = (SELECT d FROM latest))                         AS nav_prev,
        (SELECT nav FROM daily_nav
          WHERE as_of_date <= date_trunc('month', (SELECT d FROM latest))::date - INTERVAL '1 day'
          ORDER BY as_of_date DESC LIMIT 1)                                                                AS nav_mtd_anchor,
        (SELECT nav FROM daily_nav
          WHERE as_of_date <= date_trunc('year', (SELECT d FROM latest))::date - INTERVAL '1 day'
          ORDER BY as_of_date DESC LIMIT 1)                                                                AS nav_ytd_anchor
)
SELECT
    $1                                                    AS portfolio_id,
    (SELECT d FROM latest)                                AS as_of_date,
    nav_today                                             AS nav,
    CASE WHEN nav_prev          IS NULL THEN NULL
         ELSE (nav_today / nav_prev          - 1) * 100 END AS day_return_pct,
    CASE WHEN nav_mtd_anchor    IS NULL THEN NULL
         ELSE (nav_today / nav_mtd_anchor    - 1) * 100 END AS mtd_return_pct,
    CASE WHEN nav_ytd_anchor    IS NULL THEN NULL
         ELSE (nav_today / nav_ytd_anchor    - 1) * 100 END AS ytd_return_pct,
    -- AUM is the notional dollar value behind the weights. For this demo
    -- each portfolio's "AUM" is nav_today * 1_000_000 (1M base units).
    nav_today * 1000000                                   AS aum_usd
FROM anchors;
