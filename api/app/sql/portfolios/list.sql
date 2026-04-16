SELECT
    portfolio_id,
    code,
    name,
    strategy,
    benchmark,
    inception,
    base_ccy
FROM portfolios
ORDER BY code;
