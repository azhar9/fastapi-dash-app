"""FastAPI dependency providers.

The app stores pool/cache on `app.state` during startup; these helpers
pull them out for each request. Keeping them here (rather than inline in
each router) means the router signatures read as plain functions.
"""
from __future__ import annotations

import asyncpg
from fastapi import Request

from .cache import Cache
from .llm import LlmClient


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


def get_ro_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.ro_pool


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


def get_llm(request: Request) -> LlmClient | None:
    return getattr(request.app.state, "llm", None)
