"""
demo_collector.py - a synthetic option market in the exact TSETMC row format.

Use it (OPTIONS_SOURCE=demo) to work on the UI when TSETMC is unreachable, when the
market is closed, or outside Iran. It feeds the SAME parser as live data, so the whole
pipeline is exercised. The numbers are invented: underlyings are called "demo".
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

from calculator import bs_price
from config import Settings
from tsetmc_collector import TEHRAN_TZ, MarketSnapshot, parse_market_watch

# code, symbol, starting price (Rials), base implied vol, strike step
_UNDERLYINGS = (
    ("DEMO1", "نمونه۱", 24_000, 0.55, 1_000),
    ("DEMO2", "نمونه۲", 3_100, 0.70, 100),
    ("DEMO3", "نمونه۳", 9_800, 0.45, 400),
)
_EXPIRY_DAYS = (12, 40, 68)
_STRIKES_EACH_SIDE = 5


class DemoCollector:
    def __init__(self, settings: Settings, seed: int = 7) -> None:
        self._rng = random.Random(seed)
        self._r = settings.risk_free_rate
        self._q = settings.dividend_yield
        self._day_count = settings.day_count
        self._spot = {code: float(spot) for code, _sym, spot, _vol, _step in _UNDERLYINGS}
        self._volume: dict[str, int] = {}
        self._open_interest: dict[str, int] = {}

    # -- public API (same as TSETMCCollector) ---------------------------------
    async def fetch_snapshot(self) -> MarketSnapshot:
        now = datetime.now(TEHRAN_TZ)
        return parse_market_watch(self.build_payload(now.date()), fetched_at=now)

    async def aclose(self) -> None:
        return None

    # -- generator --------------------------------------------------------------
    def build_payload(self, today: date) -> dict:
        rows: list[dict] = []
        for code, symbol, spot0, base_vol, step in _UNDERLYINGS:
            self._spot[code] *= math.exp(self._rng.gauss(0.0, 0.0015))  # tiny random walk per poll
            spot = self._spot[code]
            centre = round(spot0 / step) * step
            for days in _EXPIRY_DAYS:
                expiry = today + timedelta(days=days)
                for i in range(-_STRIKES_EACH_SIDE, _STRIKES_EACH_SIDE + 1):
                    rows.append(self._row(code, symbol, spot, base_vol, centre + i * step, expiry, days, today))
        return {"instrumentOptMarketWatch": rows}

    def _side(self, key: str, price_model: float) -> dict[str, int]:
        rng = self._rng
        price = max(1, round(price_model))
        bid = max(1, round(price * 0.98))
        ask = max(bid + 1, round(price * 1.02))
        last = max(1, round(price * (1 + rng.uniform(-0.02, 0.02))))
        self._volume[key] = self._volume.get(key, rng.randint(0, 3000)) + rng.randint(0, 25)
        self._open_interest.setdefault(key, rng.randint(500, 20_000))
        return {
            "pDrCotVal": last,
            "pClosing": max(1, round(price * (1 + rng.uniform(-0.01, 0.01)))),
            "priceYesterday": max(1, round(price * (1 + rng.uniform(-0.05, 0.05)))),
            "pMeDem": bid,
            "qTitMeDem": rng.randint(1, 400),
            "pMeOf": ask,
            "qTitMeOf": rng.randint(1, 400),
            "qTotTran5J": self._volume[key],
            "qTotCap": self._volume[key] * last * 1000,
            "zTotTran": self._volume[key] // 7 + 1,
            "oP": self._open_interest[key],
            "yesterdayOP": self._open_interest[key] - rng.randint(-200, 200),
        }

    def _row(self, code, symbol, spot, base_vol, strike, expiry, days, today) -> dict:
        t = days / self._day_count
        m = math.log(strike / spot)
        iv = min(1.5, max(0.15, base_vol + 0.9 * m * m - 0.12 * m))  # smile with a mild skew
        call = bs_price(spot, strike, t, self._r, iv, "call", self._q)
        put = bs_price(spot, strike, t, self._r, iv, "put", self._q)
        tag = f"{code}-{strike}-{expiry:%y%m%d}"
        row: dict = {
            "contractSize": 1000,
            "uaInsCode": code,
            "lval30_UA": symbol,
            "pDrCotVal_UA": round(spot),
            "pClosing_UA": round(spot * 0.998),
            "priceYesterday_UA": round(spot * 0.995),
            "beginDate": (today - timedelta(days=90)).strftime("%Y%m%d"),
            "endDate": expiry.strftime("%Y%m%d"),
            "strikePrice": strike,
            "remainedDay": days,
        }
        for suffix, prefix, price in (("C", "\u0636", call), ("P", "\u0637", put)):  # ض = call, ط = put
            row[f"insCode_{suffix}"] = f"{tag}-{suffix}"
            row[f"lVal18AFC_{suffix}"] = f"{prefix}{symbol}{strike}"
            row[f"lVal30_{suffix}"] = f"{symbol}-{strike}-{expiry.isoformat()}"
            row[f"notionalValue_{suffix}"] = strike * 1000
            for field, value in self._side(f"{tag}-{suffix}", price).items():
                row[f"{field}_{suffix}"] = value
        return row
