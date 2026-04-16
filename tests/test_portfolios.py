def test_list_portfolios(client):
    r = client.get("/portfolios")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 1
    required = {"portfolio_id", "code", "name", "strategy", "benchmark", "inception", "base_ccy"}
    assert required.issubset(data[0].keys())


def test_kpis(client, any_portfolio_id):
    r = client.get(f"/portfolios/{any_portfolio_id}/kpis")
    assert r.status_code == 200
    body = r.json()
    assert body["portfolio_id"] == any_portfolio_id
    assert isinstance(body["nav"], int | float)
    assert body["nav"] > 0


def test_nav_series_monotonic_dates(client, any_portfolio_id):
    r = client.get(f"/portfolios/{any_portfolio_id}/nav")
    assert r.status_code == 200
    series = r.json()
    assert len(series) > 10
    dates = [p["as_of_date"] for p in series]
    assert dates == sorted(dates)
