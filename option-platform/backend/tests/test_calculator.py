"""Tests for the financial engine: Black-Scholes, Greeks, implied volatility, payoff."""
import math
from datetime import date

import numpy as np
import pytest

from calculator import Leg, bs_price, greeks, implied_volatility, strategy_payoff, year_fraction

# Textbook reference case: S = K = 100, T = 1 year, r = 5 %, sigma = 20 %, no dividends
S, K, T, R, SIGMA = 100.0, 100.0, 1.0, 0.05, 0.20


# -- pricing -----------------------------------------------------------------
def test_reference_prices():
    assert bs_price(S, K, T, R, SIGMA, "call") == pytest.approx(10.4506, abs=1e-4)
    assert bs_price(S, K, T, R, SIGMA, "put") == pytest.approx(5.5735, abs=1e-4)


@pytest.mark.parametrize("q", [0.0, 0.03])
def test_put_call_parity(q):
    t, strike = 0.5, 95.0
    call = bs_price(S, strike, t, R, 0.35, "call", q)
    put = bs_price(S, strike, t, R, 0.35, "put", q)
    assert call - put == pytest.approx(S * math.exp(-q * t) - strike * math.exp(-R * t), abs=1e-9)


def test_expired_option_is_intrinsic_value():
    assert bs_price(110, 100, 0.0, R, SIGMA, "call") == pytest.approx(10.0)
    assert bs_price(90, 100, 0.0, R, SIGMA, "call") == 0.0
    assert bs_price(90, 100, 0.0, R, SIGMA, "put") == pytest.approx(10.0)


def test_rejects_unknown_option_type():
    with pytest.raises(ValueError):
        bs_price(S, K, T, R, SIGMA, "straddle")  # type: ignore[arg-type]


# -- Greeks ------------------------------------------------------------------
def test_reference_greeks():
    g = greeks(S, K, T, R, SIGMA, "call")
    assert g.delta == pytest.approx(0.6368, abs=1e-4)
    assert g.gamma == pytest.approx(0.018762, abs=1e-6)
    assert g.vega == pytest.approx(0.37524, abs=1e-5)  # per 1 vol point
    assert g.theta == pytest.approx(-6.4140 / 365, abs=1e-5)  # per calendar day


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize("q", [0.0, 0.03])
def test_greeks_match_finite_differences(option_type, q):
    strike, t, sigma = 105.0, 0.4, 0.35

    def price(s=S, tt=t, vol=sigma):
        return bs_price(s, strike, tt, R, vol, option_type, q)

    g = greeks(S, strike, t, R, sigma, option_type, q, day_count=365)

    h = 0.01
    assert g.delta == pytest.approx((price(S + h) - price(S - h)) / (2 * h), rel=1e-6)
    assert g.gamma == pytest.approx((price(S + h) - 2 * price() + price(S - h)) / h**2, rel=1e-4)

    dv = 1e-5
    assert g.vega == pytest.approx((price(vol=sigma + dv) - price(vol=sigma - dv)) / (2 * dv) / 100, rel=1e-6)

    dt = 1e-5
    theta_per_year = -(price(tt=t + dt) - price(tt=t - dt)) / (2 * dt)
    assert g.theta == pytest.approx(theta_per_year / 365, rel=1e-5)


def test_call_and_put_delta_differ_by_one():
    call = greeks(S, K, T, R, SIGMA, "call")
    put = greeks(S, K, T, R, SIGMA, "put")
    assert call.delta - put.delta == pytest.approx(1.0, abs=1e-12)
    assert call.gamma == pytest.approx(put.gamma)
    assert call.vega == pytest.approx(put.vega)


# -- implied volatility ---------------------------------------------------------
@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize("strike", [80.0, 100.0, 120.0])
@pytest.mark.parametrize("sigma", [0.15, 0.45, 1.2])
@pytest.mark.parametrize("q", [0.0, 0.04])
def test_iv_round_trip(option_type, strike, sigma, q):
    t = 0.25
    price = bs_price(S, strike, t, R, sigma, option_type, q)
    iv = implied_volatility(price, S, strike, t, R, option_type, q)
    assert iv == pytest.approx(sigma, abs=1e-4)


def test_iv_is_none_below_intrinsic_value():
    # a call on 100 struck at 90 cannot be worth 5 when it is already ~11.9 in the money
    assert implied_volatility(5.0, 100.0, 90.0, 0.5, R, "call") is None


def test_iv_is_none_above_upper_bound():
    assert implied_volatility(101.0, 100.0, 90.0, 0.5, R, "call") is None


@pytest.mark.parametrize("price,t", [(0.0, 0.5), (-1.0, 0.5), (5.0, 0.0), (float("nan"), 0.5)])
def test_iv_is_none_for_unusable_inputs(price, t):
    assert implied_volatility(price, S, K, t, R, "call") is None


def test_year_fraction():
    assert year_fraction(date(2026, 11, 5), date(2026, 10, 17)) == pytest.approx(19 / 365)
    assert year_fraction(date(2026, 10, 1), date(2026, 10, 17)) == 0.0


# -- payoff -----------------------------------------------------------------
def test_long_call():
    leg = Leg(kind="call", side="long", quantity=1, price=1500, strike=24000)
    result = strategy_payoff([leg], spot=24000)
    assert result.break_evens == [25500.0]
    assert result.max_loss == pytest.approx(-1_500_000)
    assert result.profit_unbounded and result.max_profit is None
    assert not result.loss_unbounded
    assert result.net_premium == pytest.approx(-1_500_000)  # debit
    assert result.pnl_at_spot == pytest.approx(-1_500_000)
    assert np.interp(30000, result.x, result.y) == pytest.approx(4_500_000)


def test_long_put():
    leg = Leg(kind="put", side="long", quantity=2, price=900, strike=24000)
    result = strategy_payoff([leg])
    assert result.break_evens == [23100.0]
    assert result.max_loss == pytest.approx(-1_800_000)          # 2 contracts x 1000 x 900
    assert result.max_profit == pytest.approx(2 * 1000 * (24000 - 900))  # underlying goes to zero
    assert not result.profit_unbounded and not result.loss_unbounded


def test_bull_call_spread():
    legs = [
        Leg(kind="call", side="long", quantity=1, price=2500, strike=22000),
        Leg(kind="call", side="short", quantity=1, price=800, strike=26000),
    ]
    result = strategy_payoff(legs)
    assert result.break_evens == [23700.0]
    assert result.max_profit == pytest.approx((4000 - 1700) * 1000)
    assert result.max_loss == pytest.approx(-1700 * 1000)
    assert not result.profit_unbounded and not result.loss_unbounded
    assert result.net_premium == pytest.approx(-1_700_000)


def test_short_straddle_has_unbounded_loss():
    legs = [
        Leg(kind="call", side="short", quantity=1, price=1200, strike=24000),
        Leg(kind="put", side="short", quantity=1, price=1000, strike=24000),
    ]
    result = strategy_payoff(legs)
    assert result.break_evens == [21800.0, 26200.0]
    assert result.max_profit == pytest.approx(2_200_000)
    assert result.loss_unbounded and result.max_loss is None
    assert result.net_premium == pytest.approx(2_200_000)  # credit


def test_covered_call():
    legs = [
        Leg(kind="stock", side="long", quantity=1000, price=24000),
        Leg(kind="call", side="short", quantity=1, price=700, strike=26000),
    ]
    result = strategy_payoff(legs)
    assert result.break_evens == [23300.0]
    assert result.max_profit == pytest.approx((2000 + 700) * 1000)
    assert not result.profit_unbounded
    assert result.max_loss == pytest.approx((-24000 + 700) * 1000)  # stock goes to zero
    assert result.net_premium == pytest.approx(700_000)  # stock leg is not premium


def test_long_butterfly():
    legs = [
        Leg(kind="call", side="long", quantity=1, price=3000, strike=22000),
        Leg(kind="call", side="short", quantity=2, price=1700, strike=24000),
        Leg(kind="call", side="long", quantity=1, price=800, strike=26000),
    ]
    result = strategy_payoff(legs)
    assert result.break_evens == [22400.0, 25600.0]
    assert result.max_profit == pytest.approx(1_600_000)
    assert result.max_loss == pytest.approx(-400_000)
    assert not result.profit_unbounded and not result.loss_unbounded


def test_curve_contains_strikes_and_honours_explicit_range():
    leg = Leg(kind="call", side="long", quantity=1, price=1500, strike=24137)
    result = strategy_payoff([leg], x_min=20000, x_max=30000, points=11)
    assert result.x[0] == 20000 and result.x[-1] == 30000
    assert 24137.0 in result.x  # kink is drawn exactly even with a coarse grid
    assert len(result.x) == len(result.y)


@pytest.mark.parametrize(
    "legs",
    [
        [],
        [Leg(kind="call", side="long", quantity=1, price=100)],                       # option without strike
        [Leg(kind="call", side="long", quantity=0, price=100, strike=1000)],          # zero quantity
        [Leg(kind="put", side="long", quantity=1, price=-5, strike=1000)],            # negative price
    ],
)
def test_payoff_rejects_invalid_legs(legs):
    with pytest.raises(ValueError):
        strategy_payoff(legs)
