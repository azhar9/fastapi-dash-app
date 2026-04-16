-- NAV time series for a portfolio, optionally bounded by a start date.
-- $1 = portfolio_id, $2 = start_date (nullable — NULL means full history)
SELECT
    as_of_date,
    nav
FROM portfolio_nav
WHERE portfolio_id = $1
  AND ($2::date IS NULL OR as_of_date >= $2::date)
ORDER BY as_of_date;
