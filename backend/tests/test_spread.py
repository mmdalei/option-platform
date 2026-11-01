"""
M2c-1 - relative bid/ask spread.

spread_rel = (ask - bid) / mid, as a fraction (1.18 means 118 %). It is a measurement, not a
verdict: no threshold is applied here. It is None unless both sides of the book are quoted and
the book is not crossed. It describes the standing orders, so it does not depend on whether the
contract traded in the session.
Numbers below come from the real TSETMC snapshot of 2026-10-22.
"""
from datetime import date

import pytest

from chain_builder import PricingParams, _leg_payload, relative_spread
from schemas import OptionLeg
from tsetmc_collector import OptionQuote

PARAMS = PricingParams(risk_free_rate=0.30)


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


def payload_of(quote: OptionQuote) -> dict:
    return _leg_payload(quote, 68500.0, 26 / 365, 68000.0, PARAMS)


# -- relative_spread ------------------------------------------------------------------
@pytest.mark.parametrize(
    "bid,ask,expected",
    [
        (77, 300, 1.1830),        # put 38000: a spread wider than the price itself
        (8661, 8797, 0.0156),     # call 68000: a tight book
        (10671, 11582, 0.0819),   # put 80000
    ],
)
def test_relative_spread_matches_real_quotes(bid, ask, expected):
    assert relative_spread(bid, ask) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize("bid,ask", [(None, 70), (5, None), (0, 70), (5, 0), (70, 5)])
def test_relative_spread_is_none_without_a_valid_two_sided_book(bid, ask):
    assert relative_spread(bid, ask) is None


def test_locked_book_has_zero_spread():
    assert relative_spread(100, 100) == 0.0


# -- payload ----------------------------------------------------------------------------
def test_payload_carries_the_spread_of_the_book_even_without_trades():
    payload = payload_of(make_quote(bid=5.0, ask=70.0, last=35.0, close=93.0, yesterday=93.0, volume=0))
    assert payload["traded"] is False
    assert payload["spread_rel"] == pytest.approx(65 / 37.5, abs=1e-4)


def test_payload_spread_is_none_for_a_one_sided_book():
    payload = payload_of(make_quote(bid=351.0, ask=None, volume=0))
    assert payload["spread_rel"] is None


def test_payload_with_spread_matches_the_response_schema():
    payload = payload_of(make_quote(bid=8661.0, ask=8797.0, last=8711.0, close=8490.0, volume=119994))
    assert set(payload) == set(OptionLeg.model_fields)
    OptionLeg.model_validate(payload)
