def test_unknown_portfolio_returns_404(client):
    r = client.get("/portfolios/999999/kpis")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert body["instance"].endswith("/kpis")


def test_invalid_path_is_404_problem(client):
    r = client.get("/this/route/does/not/exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
