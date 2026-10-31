"""
M1 - price validity.

A contract with zero volume carries last/close over from earlier sessions. Those are
real but old prices: they stay visible in the payload, flagged by `traded=False`, and
never feed the IV solver. A real trade at 1 Rial (volume > 0) must NOT be discarded.
Numbers below come from the real TSETMC snapshot of 2026-10-22.
"""
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from chain_builder import PricingParams, _leg_payload, build_market, pick_option_price
from schemas import OptionLeg
from tsetmc_collector import TEHRAN_TZ, OptionQuote, parse_market_watch

PARAMS = PricingParams(risk_free_rate=0.30)
TODAY = date(2026, 10, 23)
FETCHED = datetime(2026, 10, 23, 11, 0, tzinfo=TEHRAN_TZ)


def make_quote(**overrides) -> OptionQuote:
    fields = dict(
        ins_code="C1", symbol="ضهرم8032", name="x", option_type="call", underlying_code="UA1",
        strike=68000.0, expiry=date(2026, 11, 18), contract_size=1000,
        last=None, close=None, yesterday=None, bid=None, ask=None,
        bid_volume=None, ask_volume=None, volume=0, value=None, trades=None,
        open_interest=None, prev_open_interest=None,
    )
    fields.update(overrides)
    return OptionQuote(**fields)


# -- pick_option_price -----------------------------------------------------------------
@pytest.mark.parametrize("source", ["mid", "last", "close"])
def test_zero_volume_carried_prices_never_feed_the_iv_solver(source):
    quote = make_quote(last=35.0, close=93.0, yesterday=93.0, volume=0)
    assert pick_option_price(quote, source) == (None, None)


def test_zero_volume_contract_with_a_two_sided_book_uses_mid():
    quote = make_quote(last=35.0, close=93.0, yesterday=93.0, bid=5.0, ask=70.0, volume=0)
    assert pick_option_price(quote, "last") == (37.5, "mid")


def test_traded_contract_keeps_last_then_close_fallbacks():
    assert pick_option_price(make_quote(last=77.0, close=139.0, volume=110), "mid") == (77.0, "last")
    assert pick_option_price(make_quote(last=None, close=139.0, volume=110), "mid") == (139.0, "close")


def test_a_real_trade_at_one_rial_is_not_discarded():
    # 2,628,625 contracts traded with last == close == 1: a real price, not a placeholder
    quote = make_quote(last=1.0, close=1.0, yesterday=1.0, bid=None, ask=1.0, volume=2_628_625)
    assert pick_option_price(quote, "mid") == (1.0, "last")


# -- _leg_payload ---------------------------------------------------------------------
def leg_of(quote: OptionQuote) -> dict:
    return _leg_payload(quote, 68500.0, 26 / 365, 68000.0, PARAMS)


def test_leg_payload_matches_the_response_schema_exactly():
    payload = leg_of(make_quote(last=35.0, close=93.0, volume=0))
    assert set(payload) == set(OptionLeg.model_fields)
    OptionLeg.model_validate(payload)


def test_carried_prices_stay_visible_but_are_flagged_and_unused():
    payload = leg_of(make_quote(last=35.0, close=93.0, yesterday=93.0, volume=0))
    assert payload["traded"] is False
    assert (payload["last"], payload["close"]) == (35.0, 93.0)  # not deleted
    assert payload["change_pct"] is None
    assert payload["price_used"] is None and payload["price_source"] is None
    assert payload["iv"] is None and payload["delta"] is None


def test_traded_contract_has_change_and_iv():
    quote = make_quote(
        option_type="put", last=4555.0, close=4778.0, yesterday=4265.0, bid=4540.0, ask=4653.0, volume=49613
    )
    payload = leg_of(quote)
    assert payload["traded"] is True
    assert payload["change_pct"] == pytest.approx((4555 / 4265 - 1) * 100, abs=0.01)
    assert payload["price_source"] == "mid" and payload["iv"] is not None


# -- parser + builder end to end --------------------------------------------------------
def call_row(strike, **side):
    row = {
        "contractSize": 1000, "uaInsCode": "UA1", "lval30_UA": "اهرم",
        "pDrCotVal_UA": 68500, "pClosing_UA": 68782, "priceYesterday_UA": 71160,
        "endDate": "20261118", "strikePrice": strike, "remainedDay": 26,
        "insCode_C": f"C{strike}", "lVal18AFC_C": f"ضهرم{strike}",
    }
    row.update({f"{name}_C": value for name, value in side.items()})
    return row


def test_end_to_end_traded_and_carried_contracts():
    traded = call_row(68000, pDrCotVal=8711, pClosing=8490, priceYesterday=9742,
                      pMeDem=8661, pMeOf=8797, qTotTran5J=119994, oP=306981)
    carried = call_row(90000, pDrCotVal=35, pClosing=93, priceYesterday=93,
                       pMeDem=0, pMeOf=0, qTotTran5J=0, oP=251)
    snapshot = parse_market_watch({"instrumentOptMarketWatch": [traded, carried]}, fetched_at=FETCHED, today=TODAY)
    chain = build_market(snapshot, PARAMS, TODAY).chains[("UA1", "2026-11-18")]
    legs = {row["strike"]: row["call"] for row in chain["rows"]}

    assert legs[68000]["traded"] is True
    assert legs[68000]["price_source"] == "mid" and legs[68000]["iv"] is not None

    assert legs[90000]["traded"] is False
    assert legs[90000]["last"] == 35.0                      # still shown
    assert legs[90000]["price_source"] is None and legs[90000]["iv"] is None
    assert legs[90000]["change_pct"] is None


# -- invariants on the latest real sample (skipped when there is none) ---------------------
SAMPLES = sorted((Path(__file__).resolve().parents[1] / "samples").glob("tsetmc_raw_*.json"))


@pytest.mark.skipif(not SAMPLES, reason="no raw sample in backend/samples (run tools/probe_tsetmc.py)")
def test_invariants_on_the_latest_real_snapshot():
    payload = json.loads(SAMPLES[-1].read_text(encoding="utf-8"))
    built = build_market(parse_market_watch(payload), PARAMS)
    seen = 0
    for chain in built.chains.values():
        for row in chain["rows"]:
            for kind in ("call", "put"):
                leg = row[kind]
                if leg is None:
                    continue
                seen += 1
                assert leg["traded"] == (leg["volume"] > 0)
                if not leg["traded"]:
                    assert leg["price_source"] in (None, "mid")
                    assert leg["change_pct"] is None
                    if leg["price_source"] is None:
                        assert leg["iv"] is None
    if seen == 0:
        pytest.skip("every contract in the sample has already expired")