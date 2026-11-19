"""
tsetmc_collector.py - fetches the whole option market from TSETMC.

Endpoint (the one used by the open-source `tseopt` client). TSETMC's API is
unofficial and can change without notice, so the parser below is deliberately
tolerant and skips rows it cannot understand instead of failing the whole poll:

    GET {base}/api/Instrument/GetInstrumentOptionMarketWatch/{market}
        market: 0 = Bourse + FaraBourse, 1 = Bourse, 2 = FaraBourse

The reply is {"instrumentOptMarketWatch": [row, ...]}. One row describes one
(underlying, strike, expiry) triple and carries BOTH sides of it:

    fields ending in _C -> call      _P -> put      _UA -> underlying asset

    insCode     instrument id        lVal18AFC  ticker          lVal30  long name
    pDrCotVal   last price           pClosing   closing price   priceYesterday
    pMeDem / qTitMeDem   best bid / size        pMeOf / qTitMeOf   best ask / size
    qTotTran5J  volume               qTotCap    traded value    zTotTran  trade count
    oP / yesterdayOP     open interest today / yesterday

All prices are Rials. TSETMC uses 0 for "no value", which becomes None here.
TSETMC may reject traffic from outside Iran, so run the collector from an Iranian
connection (your own machine is fine).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

import httpx

from config import Settings

log = logging.getLogger("collector")

# Iran abolished daylight saving time in 2022, so a fixed +03:30 offset is correct
# and avoids needing the tzdata package on Windows.
TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def tehran_today() -> date:
    return datetime.now(TEHRAN_TZ).date()


# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------
@dataclass(slots=True)
class Underlying:
    ins_code: str
    symbol: str
    last: float | None
    close: float | None
    yesterday: float | None


@dataclass(slots=True)
class OptionQuote:
    ins_code: str
    symbol: str
    name: str
    option_type: Literal["call", "put"]
    underlying_code: str
    strike: float
    expiry: date
    contract_size: int
    last: float | None
    close: float | None
    yesterday: float | None
    bid: float | None
    ask: float | None
    bid_volume: int | None
    ask_volume: int | None
    volume: int
    value: float | None
    trades: int | None
    open_interest: int | None
    prev_open_interest: int | None


@dataclass(slots=True)
class MarketSnapshot:
    fetched_at: datetime
    underlyings: dict[str, Underlying]
    options: list[OptionQuote]


# ----------------------------------------------------------------------------
# Small parsing helpers
# ----------------------------------------------------------------------------
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_COMPACT_DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})(?!\d)")
_SEPARATED_DATE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
_NAME_DATE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")


def _clean_text(value: Any) -> str:
    """Strip and map Arabic Yeh/Kaf (common in TSETMC strings) to the Persian letters."""
    return str(value or "").replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").strip()


def _first(row: dict, *names: str) -> Any:
    for name in names:
        if row.get(name) is not None:
            return row[name]
    return None


def _price(value: Any) -> float | None:
    """Rial price where 0 / missing means 'no value'."""
    if value is None:
        return None
    number = float(value)
    return number if number > 0 else None


def _count(value: Any) -> int | None:
    """Volume-like integer where 0 is a legitimate value."""
    return None if value is None else int(float(value))


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    """Solar Hijri (Jalali) -> Gregorian date (the classic jdf algorithm)."""
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    days += (jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_lengths = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > month_lengths[gm]:
        gd -= month_lengths[gm]
        gm += 1
    return date(gy, gm, gd)


def parse_date(value: Any) -> date | None:
    """
    Accepts 20261105, "20261105", "2026-11-05", "2026-11-05T00:00:00", "2026/11/05" and
    Jalali dates such as "1405/08/14" (any year below 1700 is treated as Jalali).
    """
    if value in (None, "", 0):
        return None
    text = str(value).translate(_DIGITS).strip()
    match = _COMPACT_DATE.match(text) or _SEPARATED_DATE.match(text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return jalali_to_gregorian(year, month, day) if year < 1700 else date(year, month, day)
    except ValueError:
        return None


def _resolve_expiry(end_date: Any, names: tuple[Any, ...], remained_days: Any, today: date) -> date:
    """
    Best-effort expiry date. The dedicated `endDate` field is preferred; contract names
    embed the Jalali expiry (e.g. "...-26000-1403/08/30") and `remainedDay` gives the
    days left, so either can rescue a row whose `endDate` has an unexpected format.
    """
    expiry = parse_date(end_date)
    if expiry:
        return expiry
    for name in names:
        match = _NAME_DATE.search(str(name or "").translate(_DIGITS))
        if match:
            expiry = parse_date("/".join(match.groups()))
            if expiry:
                return expiry
    if remained_days is not None:
        return today + timedelta(days=int(float(remained_days)))
    raise ValueError("cannot determine expiry date")


# ----------------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------------
def _parse_row(row: dict, today: date) -> tuple[Underlying, list[OptionQuote]]:
    ua_code = str(row["uaInsCode"])
    strike = float(row["strikePrice"])
    if strike <= 0:
        raise ValueError("non-positive strike")
    contract_size = int(float(row.get("contractSize") or 1000))
    expiry = _resolve_expiry(
        row.get("endDate"), (row.get("lVal30_C"), row.get("lVal30_P")), row.get("remainedDay"), today
    )

    underlying = Underlying(
        ins_code=ua_code,
        symbol=_clean_text(_first(row, "lval30_UA", "lVal30_UA", "lVal18AFC_UA")) or ua_code,
        last=_price(row.get("pDrCotVal_UA")),
        close=_price(row.get("pClosing_UA")),
        yesterday=_price(row.get("priceYesterday_UA")),
    )

    quotes: list[OptionQuote] = []
    for option_type, suffix in (("call", "C"), ("put", "P")):
        ins_code = row.get(f"insCode_{suffix}")
        if not ins_code:
            continue
        quotes.append(
            OptionQuote(
                ins_code=str(ins_code),
                symbol=_clean_text(row.get(f"lVal18AFC_{suffix}")) or str(ins_code),
                name=_clean_text(row.get(f"lVal30_{suffix}")),
                option_type=option_type,
                underlying_code=ua_code,
                strike=strike,
                expiry=expiry,
                contract_size=contract_size,
                last=_price(row.get(f"pDrCotVal_{suffix}")),
                close=_price(row.get(f"pClosing_{suffix}")),
                yesterday=_price(row.get(f"priceYesterday_{suffix}")),
                bid=_price(row.get(f"pMeDem_{suffix}")),
                ask=_price(row.get(f"pMeOf_{suffix}")),
                bid_volume=_count(row.get(f"qTitMeDem_{suffix}")),
                ask_volume=_count(row.get(f"qTitMeOf_{suffix}")),
                volume=_count(row.get(f"qTotTran5J_{suffix}")) or 0,
                value=_price(row.get(f"qTotCap_{suffix}")),
                trades=_count(row.get(f"zTotTran_{suffix}")),
                open_interest=_count(row.get(f"oP_{suffix}")),
                prev_open_interest=_count(row.get(f"yesterdayOP_{suffix}")),
            )
        )
    return underlying, quotes


def parse_market_watch(
    payload: dict, *, fetched_at: datetime | None = None, today: date | None = None
) -> MarketSnapshot:
    """Turn the raw TSETMC JSON into a typed snapshot."""
    fetched_at = fetched_at or datetime.now(TEHRAN_TZ)
    today = today or fetched_at.astimezone(TEHRAN_TZ).date()
    rows = payload.get("instrumentOptMarketWatch") or []

    underlyings: dict[str, Underlying] = {}
    options: list[OptionQuote] = []
    skipped = 0
    for row in rows:
        try:
            underlying, quotes = _parse_row(row, today)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            skipped += 1
            log.debug("skipping malformed row (%s): %r", exc, row)
            continue
        underlyings.setdefault(underlying.ins_code, underlying)
        options.extend(quotes)
    if skipped:
        log.warning("skipped %d malformed rows out of %d", skipped, len(rows))
    return MarketSnapshot(fetched_at=fetched_at, underlyings=underlyings, options=options)


# ----------------------------------------------------------------------------
# HTTP client
# ----------------------------------------------------------------------------
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
}


class CollectorError(RuntimeError):
    """TSETMC could not be reached or returned something unusable."""


class TSETMCCollector:
    """Fetches one full snapshot of the option market per call."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._url = (
            f"{settings.tsetmc_base_url}/api/Instrument/GetInstrumentOptionMarketWatch/"
            f"{settings.tsetmc_market}"
        )
        self._client = client or httpx.AsyncClient(
            timeout=settings.request_timeout, headers=_HEADERS, follow_redirects=True
        )

    async def fetch_snapshot(self) -> MarketSnapshot:
        snapshot = parse_market_watch(await self._get_json())
        if not snapshot.options:
            raise CollectorError("TSETMC returned no option contracts")
        return snapshot

    async def _get_json(self) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, 4):  # up to 3 tries with a short linear back-off
            try:
                response = await self._client.get(self._url)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("unexpected JSON shape")
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < 3:
                    await asyncio.sleep(attempt)
        raise CollectorError(f"TSETMC request failed: {last_error!r}") from last_error

    async def aclose(self) -> None:
        await self._client.aclose()
