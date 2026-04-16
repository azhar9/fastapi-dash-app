"""Tiny async Redis cache with a decorator.

Cache failures never fail the request: if Redis is unreachable we log a
warning and fall through to the real query. This keeps the API available
during a cache outage — a minor perf hit instead of a full outage.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis

log = logging.getLogger(__name__)


class Cache:
    def __init__(self, client: redis.Redis, default_ttl: int) -> None:
        self._client = client
        self._default_ttl = default_ttl

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(key)
        except redis.RedisError as e:
            log.warning("cache get failed", extra={"key": key, "error": str(e)})
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            await self._client.set(key, json.dumps(value, default=str), ex=ttl or self._default_ttl)
        except redis.RedisError as e:
            log.warning("cache set failed", extra={"key": key, "error": str(e)})

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except redis.RedisError:
            return False


def cache_key(namespace: str, *parts: Any) -> str:
    """Build a stable cache key. Long arg strings get hashed for readability."""
    joined = ":".join(str(p) for p in parts)
    if len(joined) > 80:
        joined = hashlib.sha1(joined.encode()).hexdigest()
    return f"portfolio:{namespace}:{joined}"


def cached(namespace: str, ttl: int | None = None) -> Callable:
    """Decorator for async endpoints. Assumes the last arg is the Cache instance.

    Usage pattern inside a router:

        @cached("portfolios.list", ttl=60)
        async def _query(pool, cache): ...

    The wrapper hashes *positional* args (skipping the first pool/cache
    parameters) into the key.
    """
    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            # Convention: fn(pool, cache, *key_args). We cache on key_args + kwargs.
            cache_obj: Cache | None = None
            for a in args:
                if isinstance(a, Cache):
                    cache_obj = a
                    break
            if cache_obj is None:
                return await fn(*args, **kwargs)
            key_parts = [a for a in args if not isinstance(a, Cache) and not _is_pool(a)]
            key_parts += [f"{k}={v}" for k, v in sorted(kwargs.items())]
            key = cache_key(namespace, *key_parts)
            hit = await cache_obj.get(key)
            if hit is not None:
                log.debug("cache hit", extra={"key": key})
                return hit
            result = await fn(*args, **kwargs)
            await cache_obj.set(key, result, ttl=ttl)
            return result
        return wrapper
    return decorator


def _is_pool(obj: Any) -> bool:
    return obj.__class__.__name__ == "Pool"


async def create_client(url: str) -> redis.Redis:
    return redis.from_url(url, encoding="utf-8", decode_responses=True)
