"""
service.py - glue between the collector, the cache, the database and websocket clients.

Every poll does the same thing:
    collector -> snapshot -> build_market (IV, Greeks, ladders)
              -> cache (one key per underlying/expiry, so a request is one cheap read)
              -> websocket subscribers of exactly the ladders they watch
              -> history table (throttled, only rows that changed)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime

from fastapi import WebSocket

from cache import MemoryCache, RedisCache
from chain_builder import BuiltMarket, PricingParams, build_market
from config import Settings
from database import Database
from tsetmc_collector import MarketSnapshot

log = logging.getLogger("service")

META_KEY = "meta:underlyings"


def chain_key(underlying_code: str, expiry_iso: str) -> str:
    return f"chain:{underlying_code}:{expiry_iso}"


class NoDataError(RuntimeError):
    """The collector has not completed a poll yet (or has stalled for longer than the TTL)."""


class NotFoundError(LookupError):
    """Unknown underlying or expiry."""


class ConnectionHub:
    """Websocket subscribers grouped by (underlying code, expiry)."""

    def __init__(self) -> None:
        self._subscribers: dict[tuple[str, str], set[WebSocket]] = defaultdict(set)

    async def connect(self, key: tuple[str, str], websocket: WebSocket) -> None:
        await websocket.accept()
        self._subscribers[key].add(websocket)

    def disconnect(self, key: tuple[str, str], websocket: WebSocket) -> None:
        subscribers = self._subscribers.get(key)
        if subscribers is None:
            return
        subscribers.discard(websocket)
        if not subscribers:
            del self._subscribers[key]

    def keys(self) -> list[tuple[str, str]]:
        return list(self._subscribers)

    async def broadcast(self, key: tuple[str, str], payload: dict) -> None:
        for websocket in list(self._subscribers.get(key, ())):
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001 - a dead client must never break the poll loop
                self.disconnect(key, websocket)


class MarketService:
    def __init__(self, settings: Settings, collector, cache: MemoryCache | RedisCache, db: Database) -> None:
        self.settings = settings
        self.collector = collector
        self.cache = cache
        self.db = db
        self.hub = ConnectionHub()
        self.params = PricingParams(
            risk_free_rate=settings.risk_free_rate,
            dividend_yield=settings.dividend_yield,
            day_count=settings.day_count,
            iv_price_source=settings.iv_price_source,
            underlying_price_source=settings.underlying_price_source,
            atm_band=settings.atm_band,
        )
        self.contract_count = 0
        self._task: asyncio.Task | None = None
        self._last_ok: float | None = None            # time.monotonic() of the last good poll
        self._last_ok_at: datetime | None = None
        self._last_error: str | None = None
        self._last_history = float("-inf")

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="market-poller")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.collector.aclose()
        await self.cache.aclose()

    async def _run(self) -> None:
        interval = self.settings.poll_interval
        while True:
            started = time.monotonic()
            try:
                snapshot = await self.collector.fetch_snapshot()
                await self.ingest(snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep polling whatever happens
                self._last_error = f"{type(exc).__name__}: {exc}"
                log.warning("poll failed: %s", self._last_error)
            await asyncio.sleep(max(0.2, interval - (time.monotonic() - started)))

    # -- one poll -----------------------------------------------------------------
    async def ingest(self, snapshot: MarketSnapshot) -> BuiltMarket:
        built = await asyncio.to_thread(build_market, snapshot, self.params)  # CPU work off the event loop

        items = {META_KEY: built.underlyings}
        items.update({chain_key(code, expiry): payload for (code, expiry), payload in built.chains.items()})
        await self.cache.set_many(items, self.settings.cache_ttl)

        self.contract_count = len(built.contracts)
        self._last_ok = time.monotonic()
        self._last_ok_at = snapshot.fetched_at
        self._last_error = None

        for key in self.hub.keys():  # push only the ladders somebody is watching
            payload = built.chains.get(key)
            if payload is not None:
                await self.hub.broadcast(key, payload)

        await self._maybe_store_history(built, snapshot.fetched_at)
        return built

    async def _maybe_store_history(self, built: BuiltMarket, ts: datetime) -> None:
        now = time.monotonic()
        if now - self._last_history < self.settings.history_interval:
            return
        self._last_history = now
        try:
            written = await asyncio.to_thread(self.db.save_snapshot, built.contracts, ts)
            log.debug("history: %d rows written", written)
        except Exception:  # noqa: BLE001 - storage problems must not stop live data
            log.exception("could not store the history snapshot")

    # -- queries used by the API --------------------------------------------------
    async def get_underlyings(self) -> list[dict]:
        meta = await self.cache.get_json(META_KEY)
        if not meta:
            raise NoDataError("no market data yet: the collector has not completed a poll")
        return meta

    async def resolve(self, underlying: str, expiry: str | None) -> tuple[str, str]:
        """Map a code or symbol (+ optional expiry) to the cache key parts. No expiry -> the nearest one."""
        meta = await self.get_underlyings()
        match = next((u for u in meta if underlying in (u["ins_code"], u["symbol"])), None)
        if match is None:
            raise NotFoundError(f"unknown underlying: {underlying}")
        expiries = [e["date"] for e in match["expiries"]]  # sorted ascending, expired ones already removed
        if expiry is None:
            return match["ins_code"], expiries[0]
        if expiry not in expiries:
            raise NotFoundError(f"unknown expiry {expiry} for {match['symbol']}")
        return match["ins_code"], expiry

    async def get_chain(self, underlying: str, expiry: str | None) -> dict:
        key = await self.resolve(underlying, expiry)
        payload = await self.cache.get_json(chain_key(*key))
        if payload is None:
            raise NoDataError("the chain expired from the cache: the collector seems to have stalled")
        return payload

    async def history(self, ins_code: str, limit: int) -> list[dict]:
        return await asyncio.to_thread(self.db.history, ins_code, limit)

    def status(self) -> dict:
        age = None if self._last_ok is None else round(time.monotonic() - self._last_ok, 1)
        if age is None:
            state = "starting"
        else:
            state = "stale" if age > max(30.0, 6 * self.settings.poll_interval) else "ok"
        return {
            "status": state,
            "source": self.settings.source,
            "last_update": self._last_ok_at.isoformat(timespec="milliseconds") if self._last_ok_at else None,
            "age_seconds": age,
            "last_error": self._last_error,
            "cache": self.cache.kind,
            "contracts": self.contract_count,
            "poll_interval": self.settings.poll_interval,
        }
