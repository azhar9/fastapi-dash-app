-- Aggregate current holdings to sector weights.
-- $1 = portfolio_id
SELECT
    s.sector,
    (SUM(h.weight) * 100)::float AS weight_pct
FROM holdings h
JOIN securities s ON s.ticker = h.ticker
WHERE h.portfolio_id = $1
  AND h.valid_to IS NULL
GROUP BY s.sector
ORDER BY weight_pct DESC;
