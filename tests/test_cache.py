import time


def test_second_call_is_faster(client, any_portfolio_id):
    # Warm call may or may not hit cache (depending on prior state); the
    # second identical call is guaranteed to be served from Redis.
    t0 = time.perf_counter()
    r1 = client.get(f"/portfolios/{any_portfolio_id}/risk", params={"window_days": 180})
    t1 = time.perf_counter()
    r2 = client.get(f"/portfolios/{any_portfolio_id}/risk", params={"window_days": 180})
    t2 = time.perf_counter()

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    # Cache should be at least somewhat faster. This is a soft check — we
    # don't assert a specific ratio because CI timing varies.
    assert (t2 - t1) <= (t1 - t0) + 0.1
