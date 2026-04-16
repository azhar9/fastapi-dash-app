"""FastAPI application factory.

The lifespan block opens the PG pool and the Redis client once at startup
and closes them on shutdown. Request handlers pull these from app.state
via the deps helpers.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .cache import Cache, create_client
from .config import get_settings
from .db import create_pool
from .errors import register_exception_handlers
from .llm import maybe_build_client
from .logging_config import configure_logging
from .middleware import RequestContextMiddleware
from .routers import ask, health, holdings, performance, portfolios, risk

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.api_log_level)
    log.info("api starting", extra={"version": "0.1.0"})

    pool    = await create_pool(settings.pg_dsn)
    ro_pool = await create_pool(settings.pg_ro_dsn)
    redis_client = await create_client(settings.redis_url)
    cache = Cache(redis_client, default_ttl=settings.api_cache_ttl_seconds)

    app.state.pool    = pool
    app.state.ro_pool = ro_pool
    app.state.cache   = cache
    app.state.redis   = redis_client
    app.state.llm     = maybe_build_client()
    if app.state.llm is None:
        log.info("GROQ_API_KEY not set — /ask endpoint will return 503")
    else:
        log.info("llm client ready")
    try:
        yield
    finally:
        log.info("api shutting down")
        await pool.close()
        await ro_pool.close()
        await redis_client.aclose()


def create_app() -> FastAPI:
    # configure_logging is also called inside lifespan, but calling it here
    # covers the narrow window before startup where uvicorn already logs.
    configure_logging(get_settings().api_log_level)

    app = FastAPI(
        title="Portfolio Analytics API",
        description="Read-only API over a demo portfolio-analytics store.",
        version="0.1.0",
        lifespan=lifespan,
    )
    # The Dash app runs on a different port, so same-origin rules would block
    # browser calls if the dashboard ever called the API directly. The Dash
    # server-side fetches through httpx so CORS isn't strictly required, but
    # opening it keeps the /docs page usable from any local origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(portfolios.router)
    app.include_router(holdings.router)
    app.include_router(performance.router)
    app.include_router(risk.router)
    app.include_router(ask.router)
    return app


app = create_app()
