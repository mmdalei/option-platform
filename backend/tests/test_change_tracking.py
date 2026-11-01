"""M2a - the service reports whether the CONTENT of the feed changes between polls.

It reports facts only (when did we last see a change); it never decides that data is "stale".
"""
import asyncio
import time
from dataclasses import replace
from datetime import datetime

import pytest

from cache import MemoryCache
from config import Settings
from database import Database
from demo_collector import DemoCollector
from service import MarketService
from tsetmc_collector import TEHRAN_TZ, parse_market_watch

CFG = Settings(source="demo", database_url="sqlite://", redis_url="")


def make_snapshot():
    now = datetime.now(TEHRAN_TZ)
    payload = DemoCollector(CFG).build_payload(now.date())
    return parse_market_watch(payload, fetched_at=now, today=now.date())


def make_service() -> MarketService:
    return MarketService(CFG, collector=None, cache=MemoryCache(), db=Database("sqlite://"))


def ingest(service: MarketService, *snapshots) -> None:
    async def run():
        for snapshot in snapshots:
            await service.ingest(snapshot)

    asyncio.run(run())


def test_status_before_the_first_poll_does_not_crash():
    status = make_service().status()
    assert status["status"] == "starting"
    assert status["change_observed"] is False
    assert status["last_change"] is None
    assert status["unchanged_seconds"] is None


def test_identical_polls_are_reported_as_unchanged():
    service, snapshot = make_service(), make_snapshot()
    ingest(service, snapshot, snapshot)
    status = service.status()
    assert status["change_observed"] is False
    assert status["last_change"] is None
    assert status["unchanged_seconds"] is not None and status["unchanged_seconds"] >= 0


@pytest.mark.parametrize("field", ["last", "bid", "ask", "volume", "open_interest"])
def test_a_changed_option_field_is_observed(field):
    service, snapshot = make_service(), make_snapshot()
    ingest(service, snapshot)
    quote = snapshot.options[0]
    setattr(quote, field, (getattr(quote, field) or 0) + 1)
    ingest(service, snapshot)
    status = service.status()
    assert status["change_observed"] is True
    assert status["last_change"] is not None
    assert status["unchanged_seconds"] < 5


def test_a_changed_underlying_price_is_observed():
    service, snapshot = make_service(), make_snapshot()
    ingest(service, snapshot)
    underlying = next(iter(snapshot.underlyings.values()))
    underlying.last = (underlying.last or 0) + 1
    ingest(service, snapshot)
    assert service.status()["change_observed"] is True


def test_the_order_of_the_rows_does_not_count_as_a_change():
    service, snapshot = make_service(), make_snapshot()
    ingest(service, snapshot)
    snapshot.options.reverse()
    ingest(service, snapshot)
    assert service.status()["change_observed"] is False


def test_unchanged_seconds_keeps_growing_while_the_feed_is_static():
    service, snapshot = make_service(), make_snapshot()
    ingest(service, snapshot)
    snapshot.options[0].last = (snapshot.options[0].last or 0) + 1
    ingest(service, snapshot)
    time.sleep(0.5)
    ingest(service, snapshot, snapshot)  # no new change
    assert service.status()["unchanged_seconds"] >= 0.4


def test_a_duplicate_row_counts_as_a_change():
    service, snapshot = make_service(), make_snapshot()
    ingest(service, snapshot)
    snapshot.options.append(replace(snapshot.options[0]))  # same contract twice
    ingest(service, snapshot)
    assert service.status()["change_observed"] is True


def test_duplicate_contracts_with_none_values_do_not_break_tracking():
    service, snapshot = make_service(), make_snapshot()
    snapshot.options.append(replace(snapshot.options[0], last=None))  # same ins_code, last is None
    ingest(service, snapshot, snapshot)  # must not raise TypeError
    assert service.status()["change_observed"] is False
