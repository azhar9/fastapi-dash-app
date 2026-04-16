"""Pytest fixtures.

The tests are integration tests: they expect docker compose to already be
running. The conftest probes /readyz once at session start and skips the
whole suite if the stack isn't up — this keeps CI failures easy to read
(one "not ready" skip instead of dozens of connection errors).
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

API_URL = os.environ.get("API_URL", "http://localhost:8000")


def _wait_for_api(timeout_s: int = 60) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API_URL}/readyz", timeout=2.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="session", autouse=True)
def _ensure_stack():
    if not _wait_for_api():
        pytest.skip(f"API at {API_URL} not reachable; skipping integration tests")


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=API_URL, timeout=10.0) as c:
        yield c


@pytest.fixture(scope="session")
def any_portfolio_id(client: httpx.Client) -> int:
    portfolios = client.get("/portfolios").json()
    assert portfolios, "seed must have inserted at least one portfolio"
    return portfolios[0]["portfolio_id"]
