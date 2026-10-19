"""
cache.py - tiny async key/value cache for the live chain payloads.

Redis is used when REDIS_URL is set and reachable; otherwise an in-process dict with
TTL takes over, so `uvicorn main:app` works out of the box on any machine (Redis has no
official Windows build, so it is optional by design).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

log = logging.getLogger("cache")


class MemoryCache:
    kind = "memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    async def get_json(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, raw = item
        if expires_at < time.monotonic():
            self._data.pop(key, None)
            return None
        return json.loads(raw)

    async def set_many(self, items: dict[str, Any], ttl: int) -> None:
        expires_at = time.monotonic() + ttl
        for key, value in items.items():
            self._data[key] = (expires_at, json.dumps(value, ensure_ascii=False))
        # opportunistic cleanup so expired expiries do not pile up
        now = time.monotonic()
        for key in [k for k, (exp, _) in self._data.items() if exp < now]:
            del self._data[key]

    async def aclose(self) -> None:
        self._data.clear()


class RedisCache:
    kind = "redis"

    def __init__(self, client) -> None:
        self._client = client

    async def get_json(self, key: str) -> Any | None:
        raw = await self._client.get(key)
        return None if raw is None else json.loads(raw)

    async def set_many(self, items: dict[str, Any], ttl: int) -> None:
        async with self._client.pipeline(transaction=False) as pipe:
            for key, value in items.items():
                pipe.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
            await pipe.execute()

    async def aclose(self) -> None:
        await self._client.aclose()


async def create_cache(redis_url: str) -> MemoryCache | RedisCache:
    """Return a Redis-backed cache if possible, else the in-process one."""
    if not redis_url:
        return MemoryCache()
    try:
        import redis.asyncio as redis  # imported lazily: only needed when configured

        client = redis.from_url(redis_url, decode_responses=True)
        await client.ping()
        log.info("using Redis cache at %s", redis_url)
        return RedisCache(client)
    except Exception as exc:  # noqa: BLE001 - any failure means "fall back"
        log.warning("Redis unavailable (%s); falling back to the in-process cache", exc)
        return MemoryCache()
