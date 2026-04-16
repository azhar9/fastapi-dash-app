def test_risk_metrics_shape(client, any_portfolio_id):
    r = client.get(f"/portfolios/{any_portfolio_id}/risk", params={"window_days": 180})
    assert r.status_code == 200
    body = r.json()
    for field in ("annualised_vol_pct", "annualised_return_pct", "sharpe",
                  "max_drawdown_pct", "var_95_pct", "beta_vs_benchmark"):
        assert field in body
    assert body["annualised_vol_pct"] >= 0
    # Drawdowns are reported as negative (or zero) percentages.
    assert body["max_drawdown_pct"] <= 0
