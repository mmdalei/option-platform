"""
chain_builder.py - turns a raw market snapshot into option-chain payloads.

For every (underlying, expiry) pair it builds a strike ladder: one row per strike with
the call and the put side by side. Every leg is enriched with implied volatility, the
Greeks and an ITM / ATM / OTM label. Everything here is synchronous and pure, so the
service runs it in a worker thread and tests can call it directly.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from calculator import greeks, implied_volatility, year_fraction
from tsetmc_collector import MarketSnapshot, OptionQuote, Underlying, tehran_today


@dataclass(frozen=True, slots=True)
class PricingParams:
    risk_free_rate: float
    dividend_yield: float = 0.0
    day_count: int = 365
    iv_price_source: str = "mid"            # which premium feeds the IV solver: mid | last | close
    underlying_price_source: str = "last"   # which underlying price is "spot": last | close
    atm_band: float = 0.01                  # |K/S - 1| below this counts as at-the-money


@dataclass(slots=True)
class BuiltMarket:
    underlyings: list[dict]                       # dashboard summary, busiest first
    chains: dict[tuple[str, str], dict]           # (underlying code, expiry ISO) -> chain payload
    contracts: list[dict]                         # flat enriched list, used for history storage


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _pct_change(price: float | None, reference: float | None) -> float | None:
    if not price or not reference:
        return None
    return round((price / reference - 1.0) * 100.0, 2)


def pick_underlying_price(underlying: Underlying, source: str) -> float | None:
    """Spot used for IV, Greeks and moneyness; falls back to the other price if one is missing."""
    order = (underlying.close, underlying.last) if source == "close" else (underlying.last, underlying.close)
    return next((price for price in order if price), None)


def pick_option_price(quote: OptionQuote, source: str) -> tuple[float | None, str | None]:
    """
    Premium fed to the IV solver and the name of the source it came from. The preferred
    source goes first; the others are fallbacks (an illiquid contract often has no bid
    or ask, or has not traded today).
    """
    mid = (quote.bid + quote.ask) / 2.0 if quote.bid and quote.ask and quote.ask >= quote.bid else None
    candidates = {"mid": mid, "last": quote.last, "close": quote.close}
    for name in [source, *(s for s in ("mid", "last", "close") if s != source)]:
        value = candidates.get(name)
        if value:
            return float(value), name
    return None, None


def classify_moneyness(
    option_type: str, spot: float | None, strike: float, atm_band: float, closest_strike: float | None
) -> str | None:
    """ITM (in profit) / ATM (at the money) / OTM (in loss) for one leg."""
    if not spot:
        return None
    if strike == closest_strike or abs(strike - spot) / spot <= atm_band:
        return "ATM"
    in_the_money = spot > strike if option_type == "call" else spot < strike
    return "ITM" if in_the_money else "OTM"


def _leg_payload(
    quote: OptionQuote, spot: float | None, years: float, closest: float | None, p: PricingParams
) -> dict:
    price, source = pick_option_price(quote, p.iv_price_source)
    iv = None
    g = None
    if spot and price and years > 0:
        iv = implied_volatility(price, spot, quote.strike, years, p.risk_free_rate, quote.option_type, p.dividend_yield)
        if iv is not None:
            g = greeks(
                spot, quote.strike, years, p.risk_free_rate, iv, quote.option_type, p.dividend_yield, p.day_count
            )
    oi_change = (
        None
        if quote.open_interest is None or quote.prev_open_interest is None
        else quote.open_interest - quote.prev_open_interest
    )
    return {
        "ins_code": quote.ins_code,
        "symbol": quote.symbol,
        "last": quote.last,
        "close": quote.close,
        "yesterday": quote.yesterday,
        "change_pct": _pct_change(quote.last, quote.yesterday),
        "bid": quote.bid,
        "ask": quote.ask,
        "bid_volume": quote.bid_volume,
        "ask_volume": quote.ask_volume,
        "volume": quote.volume,
        "value": quote.value,
        "trades": quote.trades,
        "open_interest": quote.open_interest,
        "oi_change": oi_change,
        "price_used": price,
        "price_source": source,
        "iv": _round(iv, 4),
        "delta": _round(g.delta, 4) if g else None,
        "gamma": _round(g.gamma, 8) if g else None,
        "theta": _round(g.theta, 2) if g else None,
        "vega": _round(g.vega, 2) if g else None,
        "moneyness": classify_moneyness(quote.option_type, spot, quote.strike, p.atm_band, closest),
    }


# ----------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------
def build_market(snapshot: MarketSnapshot, params: PricingParams, today: date | None = None) -> BuiltMarket:
    today = today or tehran_today()
    updated_at = snapshot.fetched_at.isoformat(timespec="milliseconds")

    # underlying -> expiry -> strike -> {"call": quote, "put": quote}
    groups: dict[tuple[str, date], dict[float, dict[str, OptionQuote]]] = defaultdict(lambda: defaultdict(dict))
    for quote in snapshot.options:
        if quote.expiry < today:  # expired contracts can linger in the feed
            continue
        groups[(quote.underlying_code, quote.expiry)][quote.strike][quote.option_type] = quote

    spot_of: dict[str, float | None] = {}
    meta_of: dict[str, dict] = {}
    for code, underlying in snapshot.underlyings.items():
        spot = pick_underlying_price(underlying, params.underlying_price_source)
        spot_of[code] = spot
        meta_of[code] = {
            "ins_code": code,
            "symbol": underlying.symbol,
            "price": spot,
            "last": underlying.last,
            "close": underlying.close,
            "yesterday": underlying.yesterday,
            "change_pct": _pct_change(underlying.last or underlying.close, underlying.yesterday),
        }

    chains: dict[tuple[str, str], dict] = {}
    contracts: list[dict] = []
    totals: dict[str, dict] = defaultdict(lambda: {"contracts": 0, "total_value": 0.0, "expiries": {}})

    for (code, expiry), by_strike in groups.items():
        underlying = snapshot.underlyings[code]
        spot = spot_of[code]
        days = (expiry - today).days
        years = year_fraction(expiry, today, params.day_count)
        strikes = sorted(by_strike)
        closest = min(strikes, key=lambda k: abs(k - spot)) if spot else None

        rows: list[dict] = []
        contract_size = 1000
        for strike in strikes:
            row: dict = {"strike": strike, "is_atm": strike == closest, "call": None, "put": None}
            for kind, quote in by_strike[strike].items():
                leg = _leg_payload(quote, spot, years, closest, params)
                row[kind] = leg
                contract_size = quote.contract_size
                totals[code]["contracts"] += 1
                totals[code]["total_value"] += quote.value or 0.0
                contracts.append(
                    {
                        **{k: leg[k] for k in ("ins_code", "symbol", "last", "bid", "ask", "volume", "open_interest", "iv", "delta")},
                        "name": quote.name,
                        "option_type": quote.option_type,
                        "underlying_code": code,
                        "underlying_symbol": underlying.symbol,
                        "underlying_price": spot,
                        "strike": quote.strike,
                        "expiry": expiry,
                        "contract_size": quote.contract_size,
                    }
                )
            rows.append(row)

        totals[code]["expiries"][expiry.isoformat()] = days
        chains[(code, expiry.isoformat())] = {
            "underlying": meta_of[code],
            "expiry": expiry.isoformat(),
            "days_to_expiry": days,
            "contract_size": contract_size,
            "updated_at": updated_at,
            "params": {
                "risk_free_rate": params.risk_free_rate,
                "dividend_yield": params.dividend_yield,
                "iv_price_source": params.iv_price_source,
                "underlying_price_source": params.underlying_price_source,
            },
            "rows": rows,
        }

    underlyings = [
        {
            **meta_of[code],
            "contracts": agg["contracts"],
            "total_value": agg["total_value"],
            "expiries": [{"date": iso, "days": d} for iso, d in sorted(agg["expiries"].items())],
        }
        for code, agg in totals.items()
    ]
    underlyings.sort(key=lambda u: u["total_value"], reverse=True)
    return BuiltMarket(underlyings=underlyings, chains=chains, contracts=contracts)
