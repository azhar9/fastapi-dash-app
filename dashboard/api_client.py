"""Thin HTTP client around the FastAPI backend.

A single module-level httpx.Client keeps a keep-alive connection pool.
All callers go through the `ApiError` wrapper so Dash callbacks can
render a friendly error rather than leaking a stack trace.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

API_BASE_URL = os.environ.get("API_BASE_URL", "http://api:8000")
_client = httpx.Client(base_url=API_BASE_URL, timeout=10.0)


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


def _get(path: str, **params: Any) -> Any:
    try:
        r = _client.get(path, params={k: v for k, v in params.items() if v is not None})
    except httpx.HTTPError as e:
        log.warning("api call failed: %s %s -> %s", path, params, e)
        raise ApiError(0, f"Could not reach API ({e.__class__.__name__})") from e
    if r.status_code >= 400:
        try:
            body = r.json()
            detail = body.get("detail") or body.get("title") or r.text
        except ValueError:
            detail = r.text
        raise ApiError(r.status_code, detail)
    return r.json()


def list_portfolios() -> list[dict]:
    return _get("/portfolios")


def get_kpis(portfolio_id: int) -> dict:
    return _get(f"/portfolios/{portfolio_id}/kpis")


def get_nav(portfolio_id: int, start: str | None = None) -> list[dict]:
    return _get(f"/portfolios/{portfolio_id}/nav", start=start)


def get_holdings(portfolio_id: int) -> list[dict]:
    return _get(f"/portfolios/{portfolio_id}/holdings")


def get_sectors(portfolio_id: int) -> list[dict]:
    return _get(f"/portfolios/{portfolio_id}/holdings/sectors")


def get_vs_benchmark(portfolio_id: int, start: str | None = None) -> list[dict]:
    return _get(f"/portfolios/{portfolio_id}/performance/vs-benchmark", start=start)


def get_rolling(portfolio_id: int, window_days: int = 60) -> list[dict]:
    return _get(f"/portfolios/{portfolio_id}/performance/rolling", window_days=window_days)


def get_risk(portfolio_id: int, window_days: int = 365) -> dict:
    return _get(f"/portfolios/{portfolio_id}/risk", window_days=window_days)


def ask(question: str) -> dict:
    try:
        r = _client.post("/ask", json={"question": question}, timeout=30.0)
    except httpx.HTTPError as e:
        log.warning("ask call failed: %s", e)
        raise ApiError(0, f"Could not reach API ({e.__class__.__name__})") from e
    if r.status_code >= 400:
        try:
            body = r.json()
            detail = body.get("detail") or body.get("title") or r.text
        except ValueError:
            detail = r.text
        raise ApiError(r.status_code, detail)
    return r.json()
