def test_vs_benchmark_has_both_series(client, any_portfolio_id):
    rows = client.get(f"/portfolios/{any_portfolio_id}/performance/vs-benchmark").json()
    assert len(rows) > 10
    first = rows[0]
    assert "portfolio_cum_return_pct" in first
    assert "benchmark_cum_return_pct" in first
    # First day is the rebase anchor → should be 0 for both series.
    assert abs(first["portfolio_cum_return_pct"]) < 1e-6
    assert abs(first["benchmark_cum_return_pct"]) < 1e-6


def test_rolling_metrics_honor_window(client, any_portfolio_id):
    rows = client.get(
        f"/portfolios/{any_portfolio_id}/performance/rolling",
        params={"window_days": 30},
    ).json()
    # First (window-1) days should have NULL metrics (we haven't seen the
    # required number of observations yet).
    assert rows[0]["rolling_vol_pct"] is None
    # Somewhere deep into the series we should have non-null values.
    assert any(r["rolling_vol_pct"] is not None for r in rows)


def test_rolling_window_validation(client, any_portfolio_id):
    # window_days must be between 5 and 252 per the route.
    r = client.get(
        f"/portfolios/{any_portfolio_id}/performance/rolling",
        params={"window_days": 1000},
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
