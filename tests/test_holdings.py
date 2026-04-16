def test_holdings_has_expected_columns(client, any_portfolio_id):
    rows = client.get(f"/portfolios/{any_portfolio_id}/holdings").json()
    assert len(rows) >= 1
    cols = {"ticker", "name", "sector", "weight_pct", "price", "market_value"}
    assert cols.issubset(rows[0].keys())


def test_weights_sum_to_100(client, any_portfolio_id):
    rows = client.get(f"/portfolios/{any_portfolio_id}/holdings").json()
    total = sum(r["weight_pct"] for r in rows)
    # Weights are stored rounded to 6 decimals; leave a small tolerance.
    assert abs(total - 100.0) < 0.01, f"weights summed to {total}, expected ~100"


def test_sector_breakdown_sums_to_100(client, any_portfolio_id):
    rows = client.get(f"/portfolios/{any_portfolio_id}/holdings/sectors").json()
    total = sum(r["weight_pct"] for r in rows)
    assert abs(total - 100.0) < 0.01
