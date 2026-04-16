"""Global exception handlers returning RFC 7807 problem+json responses.

Every error response the API produces goes through one of these handlers,
so the shape is consistent for clients and we have one place to log.
"""
from __future__ import annotations

import logging
import traceback

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"


def _problem(
    request: Request,
    status: int,
    title: str,
    detail: str,
    type_: str = "about:blank",
    **extra,
) -> JSONResponse:
    body = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": str(request.url.path),
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_CONTENT_TYPE)


class AppError(Exception):
    """Base for domain errors we raise ourselves (mapped to 4xx)."""
    status_code = 400
    title = "Bad Request"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    status_code = 404
    title = "Not Found"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        log.info(
            "app error",
            extra={"status": exc.status_code, "title": exc.title, "detail": exc.detail},
        )
        return _problem(request, exc.status_code, exc.title, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            request,
            exc.status_code,
            exc.detail if isinstance(exc.detail, str) else "HTTP error",
            str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Re-shape pydantic errors into the problem-details "errors" extension
        # so clients still get the per-field info.
        return _problem(
            request,
            422,
            "Validation Error",
            "One or more request parameters are invalid.",
            errors=exc.errors(),
        )

    @app.exception_handler(asyncpg.PostgresError)
    async def _pg(request: Request, exc: asyncpg.PostgresError) -> JSONResponse:
        # Never leak the raw SQL / internal message to the caller. Log it,
        # return a generic 500.
        log.error(
            "postgres error",
            extra={"sqlstate": getattr(exc, "sqlstate", None)},
            exc_info=exc,
        )
        return _problem(
            request,
            500,
            "Database Error",
            "A database error occurred. The incident has been logged.",
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled exception\n%s", traceback.format_exc())
        return _problem(
            request,
            500,
            "Internal Server Error",
            "An unexpected error occurred. The incident has been logged.",
        )
