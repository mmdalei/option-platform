"""
calculator.py - financial engine.

Black-Scholes-Merton pricing, Greeks, implied volatility (IV) and the expiry payoff
of multi-leg strategies. Pure functions with no I/O, so everything is easy to test.

Conventions
-----------
* Prices and strikes are in Rials, exactly as TSETMC publishes them.
* Equity options on the Tehran exchange are European-style (exercise only at
  expiry), which is exactly what Black-Scholes assumes.
* T is in years: calendar days left / day_count.
* Vega is quoted per 1 volatility point (1 %); theta per calendar day.
* q is a continuous dividend yield (0 when the underlying pays no dividend).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal, Sequence

import numpy as np
from scipy.optimize import brentq

OptionType = Literal["call", "put"]
LegKind = Literal["call", "put", "stock"]
Side = Literal["long", "short"]

_SQRT2 = math.sqrt(2.0)
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

IV_MIN = 1e-4  # 0.01 %  - lower end of the IV search bracket
IV_MAX = 5.0   # 500 %   - upper end of the IV search bracket


# ----------------------------------------------------------------------------
# Black-Scholes-Merton
# ----------------------------------------------------------------------------
def _cdf(x: float) -> float:
    """Standard normal CDF. math.erf is ~100x faster than scipy.stats for scalars."""
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _pdf(x: float) -> float:
    """Standard normal density."""
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)


def _check_type(option_type: str) -> None:
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float, q: float) -> tuple[float, float]:
    vol_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_sqrt_t
    return d1, d1 - vol_sqrt_t


def bs_price(
    S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType, q: float = 0.0
) -> float:
    """Theoretical premium per share (Rials)."""
    _check_type(option_type)
    T = max(T, 0.0)
    disc_s = S * math.exp(-q * T)
    disc_k = K * math.exp(-r * T)
    if T == 0.0 or sigma <= 0.0:
        # Degenerate case: no randomness left, so value = discounted intrinsic value.
        return max(disc_s - disc_k, 0.0) if option_type == "call" else max(disc_k - disc_s, 0.0)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    if option_type == "call":
        return disc_s * _cdf(d1) - disc_k * _cdf(d2)
    return disc_k * _cdf(-d2) - disc_s * _cdf(-d1)


@dataclass(frozen=True, slots=True)
class Greeks:
    delta: float
    gamma: float  # change of delta per 1 Rial move of the underlying
    theta: float  # Rials per share, per calendar day
    vega: float   # Rials per share, per 1 volatility point (1 %)


def greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0,
    day_count: int = 365,
) -> Greeks:
    """Delta, Gamma, Theta and Vega of a European option (Merton dividend form)."""
    _check_type(option_type)
    if T <= 0.0 or sigma <= 0.0:
        if option_type == "call":
            delta = 1.0 if S > K else 0.0
        else:
            delta = -1.0 if S < K else 0.0
        return Greeks(delta, 0.0, 0.0, 0.0)

    sqrt_t = math.sqrt(T)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    carry = math.exp(-q * T)
    disc_s = S * carry
    disc_k = K * math.exp(-r * T)
    pdf_d1 = _pdf(d1)

    gamma = carry * pdf_d1 / (S * sigma * sqrt_t)
    vega = disc_s * pdf_d1 * sqrt_t / 100.0
    decay = -disc_s * pdf_d1 * sigma / (2.0 * sqrt_t)

    if option_type == "call":
        delta = carry * _cdf(d1)
        theta_year = decay - r * disc_k * _cdf(d2) + q * disc_s * _cdf(d1)
    else:
        delta = -carry * _cdf(-d1)
        theta_year = decay + r * disc_k * _cdf(-d2) - q * disc_s * _cdf(-d1)
    return Greeks(delta, gamma, theta_year / day_count, vega)


def implied_volatility(
    price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType,
    q: float = 0.0,
    *,
    tol: float = 1e-8,
) -> float | None:
    """
    Implied volatility (annualised, 0.55 = 55 %) that reproduces `price`, or None when
    no sensible value exists: expired option, price outside the no-arbitrage bounds,
    or an IV outside [IV_MIN, IV_MAX].

    Brent's method on a fixed bracket: slower than Newton on paper but it cannot
    diverge, which matters for the illiquid, widely-spread quotes of this market.
    """
    _check_type(option_type)
    values = (price, S, K, T, r, q)
    if not all(math.isfinite(v) for v in values):
        return None
    if price <= 0.0 or S <= 0.0 or K <= 0.0 or T <= 0.0:
        return None

    disc_s = S * math.exp(-q * T)
    disc_k = K * math.exp(-r * T)
    if option_type == "call":
        lower, upper = max(disc_s - disc_k, 0.0), disc_s
    else:
        lower, upper = max(disc_k - disc_s, 0.0), disc_k
    if price <= lower or price >= upper:
        return None  # quote violates the no-arbitrage bounds -> IV undefined

    def objective(sigma: float) -> float:
        return bs_price(S, K, T, r, sigma, option_type, q) - price

    if objective(IV_MIN) > 0.0 or objective(IV_MAX) < 0.0:
        return None
    try:
        return float(brentq(objective, IV_MIN, IV_MAX, xtol=tol, maxiter=100))
    except (ValueError, RuntimeError):
        return None


def year_fraction(expiry: date, today: date, day_count: int = 365) -> float:
    """Calendar days left divided by day_count; never negative."""
    return max((expiry - today).days, 0) / day_count


# ----------------------------------------------------------------------------
# Strategy payoff at expiry (profit / loss diagram)
# ----------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Leg:
    """
    One position of a strategy.

    kind           "call" | "put" | "stock"
    side           "long" (bought) | "short" (sold)
    quantity       contracts for options, shares for stock
    price          premium per share for options, entry price for stock
    strike         required for options
    contract_size  shares per option contract (1000 on the Tehran exchange)
    """

    kind: LegKind
    side: Side
    quantity: float
    price: float
    strike: float | None = None
    contract_size: int = 1000


@dataclass(frozen=True, slots=True)
class PayoffResult:
    x: list[float]                 # underlying price at expiry
    y: list[float]                 # strategy profit / loss in Rials
    break_evens: list[float]       # every price where P/L crosses zero
    max_profit: float | None       # best P/L over all prices; None if unbounded
    max_loss: float | None         # worst P/L over all prices (negative = loss); None if unbounded
    profit_unbounded: bool
    loss_unbounded: bool
    net_premium: float             # option premium flow: > 0 credit received, < 0 debit paid
    pnl_at_spot: float | None      # P/L if the underlying is still at `spot` at expiry


def _validate_leg(leg: Leg) -> None:
    if leg.kind not in ("call", "put", "stock"):
        raise ValueError(f"unknown leg kind {leg.kind!r}")
    if leg.side not in ("long", "short"):
        raise ValueError(f"unknown leg side {leg.side!r}")
    if not leg.quantity > 0:
        raise ValueError("quantity must be positive")
    if leg.price < 0:
        raise ValueError("price must not be negative")
    if leg.kind != "stock" and (leg.strike is None or not leg.strike > 0):
        raise ValueError("options need a positive strike")
    if leg.contract_size <= 0:
        raise ValueError("contract_size must be positive")


def _sign(leg: Leg) -> float:
    return 1.0 if leg.side == "long" else -1.0


def _shares(leg: Leg) -> float:
    return leg.quantity * (1 if leg.kind == "stock" else leg.contract_size)


def leg_pnl(leg: Leg, spot_at_expiry: np.ndarray | Sequence[float]) -> np.ndarray:
    """P/L of one leg at expiry for each underlying price (vectorised)."""
    s = np.asarray(spot_at_expiry, dtype=float)
    if leg.kind == "call":
        value = np.maximum(s - leg.strike, 0.0)
    elif leg.kind == "put":
        value = np.maximum(leg.strike - s, 0.0)
    else:
        value = s
    return _sign(leg) * _shares(leg) * (value - leg.price)


def _total_pnl(legs: Sequence[Leg], s: np.ndarray) -> np.ndarray:
    return np.sum([leg_pnl(leg, s) for leg in legs], axis=0)


def _break_evens(xs: np.ndarray, ys: np.ndarray, slope_right: float) -> list[float]:
    """
    Exact zero crossings of a piecewise-linear P/L curve.

    `xs` are the kinks of the curve (0 and every strike). Between kinks the curve is a
    straight line, so linear interpolation is exact; beyond the last kink the curve
    continues with `slope_right`.
    """
    eps = 1e-9 * max(1.0, float(np.max(np.abs(ys))))
    z = np.where(np.abs(ys) <= eps, 0.0, ys)  # treat float noise as exact zero
    roots: list[float] = []
    for i in range(len(xs) - 1):
        y0, y1 = z[i], z[i + 1]
        if y0 == 0.0:
            if i == 0 or z[i - 1] != 0.0:  # first point of a flat-zero stretch
                roots.append(float(xs[i]))
        elif y0 * y1 < 0.0:
            roots.append(float(xs[i] - y0 * (xs[i + 1] - xs[i]) / (y1 - y0)))

    x_last, y_last = float(xs[-1]), float(z[-1])
    if y_last == 0.0:
        if len(xs) == 1 or z[-2] != 0.0:
            roots.append(x_last)
    elif abs(slope_right) > 1e-12:
        tail_root = x_last - y_last / slope_right  # open-ended segment to +infinity
        if tail_root > x_last:
            roots.append(tail_root)

    unique = sorted({round(root, 6) for root in roots if root > 1e-9})
    return unique


def strategy_payoff(
    legs: Sequence[Leg],
    *,
    spot: float | None = None,
    x_min: float | None = None,
    x_max: float | None = None,
    points: int = 201,
) -> PayoffResult:
    """
    Profit / loss of a multi-leg strategy at expiry.

    Returns the (x, y) points to plot plus exact summary figures. The curve is
    piecewise linear with kinks at the strikes, so break-evens and the maximum
    profit / loss are computed analytically instead of being read off the grid.
    """
    if not legs:
        raise ValueError("at least one leg is required")
    for leg in legs:
        _validate_leg(leg)
    if points < 2:
        raise ValueError("points must be at least 2")

    strikes = sorted({float(leg.strike) for leg in legs if leg.kind != "stock"})
    references = [*strikes, *(leg.price for leg in legs if leg.kind == "stock")]
    if spot:
        references.append(spot)

    lo = x_min if x_min is not None else max(0.0, 0.6 * min(references))
    hi = x_max if x_max is not None else 1.4 * max(references)
    if not hi > lo:
        raise ValueError("x_max must be greater than x_min")

    # Plot grid: even steps plus the exact strikes, so the kinks are drawn precisely.
    inside = [k for k in strikes if lo < k < hi]
    grid = np.unique(np.concatenate([np.linspace(lo, hi, points), inside]))
    pnl = _total_pnl(legs, grid)

    # Behaviour for very high prices: only calls and stock keep a non-zero slope.
    slope_right = sum(_sign(leg) * _shares(leg) for leg in legs if leg.kind in ("call", "stock"))
    profit_unbounded = slope_right > 1e-12
    loss_unbounded = slope_right < -1e-12

    # All extremes of a piecewise-linear curve sit on its kinks (0 and the strikes).
    kinks = np.array([0.0, *strikes])
    kink_pnl = _total_pnl(legs, kinks)
    max_profit = None if profit_unbounded else float(kink_pnl.max())
    max_loss = None if loss_unbounded else float(kink_pnl.min())

    net_premium = sum(
        -_sign(leg) * leg.price * _shares(leg) for leg in legs if leg.kind != "stock"
    )
    pnl_at_spot = float(_total_pnl(legs, np.array([spot]))[0]) if spot else None

    return PayoffResult(
        x=grid.tolist(),
        y=pnl.tolist(),
        break_evens=_break_evens(kinks, kink_pnl, slope_right),
        max_profit=max_profit,
        max_loss=max_loss,
        profit_unbounded=profit_unbounded,
        loss_unbounded=loss_unbounded,
        net_premium=float(net_premium),
        pnl_at_spot=pnl_at_spot,
    )
