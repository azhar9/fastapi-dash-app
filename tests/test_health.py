def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_reports_services(client):
    body = client.get("/readyz").json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert body["redis"] is True


def test_request_id_header_echoed(client):
    r = client.get("/healthz", headers={"X-Request-ID": "rid-abc-123"})
    assert r.headers["X-Request-ID"] == "rid-abc-123"


def test_request_id_generated_when_absent(client):
    r = client.get("/healthz")
    rid = r.headers.get("X-Request-ID")
    assert rid and len(rid) >= 8
