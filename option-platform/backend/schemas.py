"""
schemas.py - request / response models of the HTTP API (they also drive /docs).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Moneyness = Literal["ITM", "ATM", "OTM"]


# ----------------------------------------------------------------------------
# Payoff calculator
# ----------------------------------------------------------------------------
class PayoffLegIn(BaseModel):
    kind: Literal["call", "put", "stock"]
    side: Literal["long", "short"]
    quantity: float = Field(gt=0, description="Contracts for options, shares for stock")
    price: float = Field(ge=0, description="Premium per share (options) or entry price (stock), in Rials")
    strike: float | None = Field(default=None, gt=0)
    contract_size: int = Field(default=1000, gt=0)

    @model_validator(mode="after")
    def _options_need_a_strike(self) -> "PayoffLegIn":
        if self.kind != "stock" and self.strike is None:
            raise ValueError("strike is required for call and put legs")
        return self


class PayoffRequest(BaseModel):
    legs: list[PayoffLegIn] = Field(min_length=1, max_length=12)
    spot: float | None = Field(default=None, gt=0, description="Current underlying price; adds pnl_at_spot")
    x_min: float | None = Field(default=None, ge=0)
    x_max: float | None = Field(default=None, gt=0)
    points: int = Field(default=201, ge=11, le=2001)

    @model_validator(mode="after")
    def _range_is_ordered(self) -> "PayoffRequest":
        if self.x_min is not None and self.x_max is not None and self.x_min >= self.x_max:
            raise ValueError("x_max must be greater than x_min")
        return self


class PayoffResponse(BaseModel):
    x: list[float]
    y: list[float]
    break_evens: list[float]
    max_profit: float | None
    max_loss: float | None
    profit_unbounded: bool
    loss_unbounded: bool
    net_premium: float
    pnl_at_spot: float | None


# ----------------------------------------------------------------------------
# Option chain
# ----------------------------------------------------------------------------
class OptionLeg(BaseModel):
    ins_code: str
    symbol: str
    last: float | None
    close: float | None
    yesterday: float | None
    change_pct: float | None
    bid: float | None
    ask: float | None
    bid_volume: int | None
    ask_volume: int | None
    volume: int
    value: float | None
    trades: int | None
    open_interest: int | None
    oi_change: int | None
    price_used: float | None
    price_source: Literal["mid", "last", "close"] | None
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    moneyness: Moneyness | None


class ChainRow(BaseModel):
    strike: float
    is_atm: bool
    call: OptionLeg | None
    put: OptionLeg | None


class UnderlyingQuote(BaseModel):
    ins_code: str
    symbol: str
    price: float | None
    last: float | None
    close: float | None
    yesterday: float | None
    change_pct: float | None


class ExpiryInfo(BaseModel):
    date: str  # ISO yyyy-mm-dd
    days: int


class UnderlyingMeta(UnderlyingQuote):
    contracts: int
    total_value: float
    expiries: list[ExpiryInfo]


class ChainResponse(BaseModel):
    underlying: UnderlyingQuote
    expiry: str
    days_to_expiry: int
    contract_size: int
    updated_at: str
    params: dict[str, float | str]
    rows: list[ChainRow]
