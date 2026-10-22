"""Chain builder and API tests. Uses the demo collector, which emits the TSETMC row format."""
import json
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from chain_builder import PricingParams, build_market
from config import Settings
from demo_collector import DemoCollector
from main import create_app
from schemas import ChainResponse, UnderlyingMeta
from tsetmc_collector import TEHRAN_TZ, parse_market_watch

CFG = Settings(
    source="demo",
    database_url="sqlite://",   # in-memory
    redis_url="",
    poll_interval=0.2,
    history_interval=0.0,
    cache_ttl=30,
)
PARAMS = PricingParams(
    risk_free_rate=CFG.risk_free_rate,
    dividend_yield=CFG.dividend_yield,
    day_count=CFG.day_count,
    iv_price_source="mid",
    underlying_price_source="last",
    atm_band=CFG.atm_band,
)


@pytest.fixture()
def snapshot():
    now = datetime.now(TEHRAN_TZ)
    payload = DemoCollector(CFG).build_payload(now.date())
    return parse_market_watch(payload, fetched_at=now, today=now.date())


# -- chain builder --------------------------------------------------------------------
def test_structure_of_the_built_market(snapshot):
    built = build_market(snapshot, PARAMS, snapshot.fetched_at.date())
    assert len(built.underlyings) == 3
    assert len(built.chains) == 9  # 3 underlyings x 3 expiries
    for chain in built.chains.values():
        strikes = [row["strike"] for row in chain["rows"]]
        assert strikes == sorted(strikes) and len(strikes) == 11
        assert all(row["call"] and row["put"] for row in chain["rows"])
        assert sum(row["is_atm"] for row in chain["rows"]) == 1


def test_everything_is_json_serialisable_and_matches_the_response_schema(snapshot):
    built = build_market(snapshot, PARAMS, snapshot.fetched_at.date())
    json.dumps(built.underlyings)
    for meta in built.underlyings:
        UnderlyingMeta.model_validate(meta)
    for chain in built.chains.values():
        json.dumps(chain)
        ChainResponse.model_validate(chain)


def test_moneyness_labels_follow_the_strike_and_spot(snapshot):
    built = build_market(snapshot, PARAMS, snapshot.fetched_at.date())
    for chain in built.chains.values():
        spot = chain["underlying"]["price"]
        atm_strike = next(row["strike"] for row in chain["rows"] if row["is_atm"])
        for row in chain["rows"]:
            for kind in ("call", "put"):
                label = row[kind]["moneyness"]
                if row["strike"] == atm_strike or abs(row["strike"] - spot) / spot <= PARAMS.atm_band:
                    assert label == "ATM"
                elif kind == "call":
                    assert label == ("ITM" if spot > row["strike"] else "OTM")
                else:
                    assert label == ("ITM" if spot < row["strike"] else "OTM")


def test_implied_vol_is_recovered_near_the_money(snapshot):
    built = build_market(snapshot, PARAMS, snapshot.fetched_at.date())
    chain = built.chains[("DEMO1", min(e for (c, e) in built.chains if c == "DEMO1"))]
    atm = next(row for row in chain["rows"] if row["is_atm"])
    # the demo market is generated with a 55 % base vol and a mild smile
    assert atm["call"]["iv"] == pytest.approx(0.55, abs=0.02)
    assert atm["put"]["iv"] == pytest.approx(0.55, abs=0.02)
    assert 0 < atm["call"]["delta"] < 1 and -1 < atm["put"]["delta"] < 0
    assert atm["call"]["gamma"] > 0 and atm["call"]["vega"] > 0 and atm["call"]["theta"] < 0


def test_price_source_falls_back_when_no_quotes(snapshot):
    quote = snapshot.options[0]
    quote.bid = quote.ask = None
    built = build_market(snapshot, PARAMS, snapshot.fetched_at.date())
    leg = next(
        row[quote.option_type]
        for chain in built.chains.values()
        for row in chain["rows"]
        if row[quote.option_type] and row[quote.option_type]["ins_code"] == quote.ins_code
    )
    assert leg["price_source"] == "last"


def test_expired_contracts_are_dropped(snapshot):
    tomorrow = snapshot.fetched_at.date() + timedelta(days=500)
    built = build_market(snapshot, PARAMS, today=tomorrow)
    assert built.chains == {} and built.underlyings == []


# -- API ---------------------------------------------------------------------------------
@pytest.fixture()
def client():
    with TestClient(create_app(CFG)) as test_client:
        for _ in range(60):  # wait for the first poll
            if test_client.get("/api/underlyings").status_code == 200:
                break
            time.sleep(0.1)
        yield test_client


def first_chain(client):
    meta = client.get("/api/underlyings").json()[0]
    expiry = meta["expiries"][0]["date"]
    return meta, expiry


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["source"] == "demo" and body["cache"] == "memory"
    assert body["contracts"] == 198  # 3 underlyings x 3 expiries x 11 strikes x 2 sides


def test_underlyings_and_chain(client):
    meta, expiry = first_chain(client)
    assert len(client.get("/api/underlyings").json()) == 3

    by_code = client.get("/api/option-chain", params={"underlying": meta["ins_code"], "expiry": expiry})
    assert by_code.status_code == 200
    chain = by_code.json()
    assert chain["expiry"] == expiry and len(chain["rows"]) == 11

    # the symbol works as an identifier, and the nearest expiry is the default
    by_symbol = client.get("/api/option-chain", params={"underlying": meta["symbol"]})
    assert by_symbol.status_code == 200
    assert by_symbol.json()["expiry"] == expiry


def test_unknown_underlying_and_expiry_are_404(client):
    meta, _ = first_chain(client)
    assert client.get("/api/option-chain", params={"underlying": "nope"}).status_code == 404
    bad_expiry = client.get("/api/option-chain", params={"underlying": meta["ins_code"], "expiry": "1999-01-01"})
    assert bad_expiry.status_code == 404


def test_payoff_endpoint(client):
    body = {
        "spot": 24000,
        "legs": [
            {"kind": "call", "side": "long", "quantity": 1, "price": 2500, "strike": 22000},
            {"kind": "call", "side": "short", "quantity": 1, "price": 800, "strike": 26000},
        ],
    }
    response = client.post("/api/payoff", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["break_evens"] == [23700.0]
    assert data["max_profit"] == pytest.approx(2_300_000)
    assert data["max_loss"] == pytest.approx(-1_700_000)
    assert len(data["x"]) == len(data["y"]) > 100


def test_payoff_validation_errors(client):
    no_strike = {"legs": [{"kind": "call", "side": "long", "quantity": 1, "price": 100}]}
    assert client.post("/api/payoff", json=no_strike).status_code == 422
    assert client.post("/api/payoff", json={"legs": []}).status_code == 422
    backwards = {
        "legs": [{"kind": "stock", "side": "long", "quantity": 1, "price": 100}],
        "x_min": 200,
        "x_max": 100,
    }
    assert client.post("/api/payoff", json=backwards).status_code == 422


def test_websocket_pushes_the_chain_and_then_updates(client):
    meta, expiry = first_chain(client)
    with client.websocket_connect(f"/ws/option-chain/{meta['ins_code']}?expiry={expiry}") as ws:
        first = ws.receive_json()
        assert first["expiry"] == expiry and len(first["rows"]) == 11
        second = ws.receive_json()  # pushed by the next poll
        assert second["updated_at"] != first["updated_at"]


def test_history_is_stored(client):
    meta, expiry = first_chain(client)
    chain = client.get("/api/option-chain", params={"underlying": meta["ins_code"], "expiry": expiry}).json()
    ins_code = chain["rows"][0]["call"]["ins_code"]
    time.sleep(0.7)  # a few polls
    rows = client.get(f"/api/contracts/{ins_code}/history", params={"limit": 50}).json()
    assert len(rows) >= 1
    assert rows == sorted(rows, key=lambda r: r["ts"])  # oldest first
