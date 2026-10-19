"""Tests for the TSETMC parser: row layout, date formats, Jalali conversion."""
from datetime import date, datetime, timedelta

import pytest

from tsetmc_collector import TEHRAN_TZ, _clean_text, jalali_to_gregorian, parse_date, parse_market_watch

TODAY = date(2026, 10, 17)


def make_row(**overrides) -> dict:
    """One instrumentOptMarketWatch row in the layout used by TSETMC."""
    row = {
        "contractSize": 1000,
        "uaInsCode": "UA1",
        "lval30_UA": "اهرم",
        "pDrCotVal_UA": 24000,
        "pClosing_UA": 23900,
        "priceYesterday_UA": 23800,
        "beginDate": "20260101",
        "endDate": "20261105",
        "strikePrice": 24000,
        "remainedDay": 19,
        # call side: actively traded
        "insCode_C": "C1",
        "lVal18AFC_C": "ضهرم2400",
        "lVal30_C": "اختيارخ اهرم-24000-1405/08/14",
        "pDrCotVal_C": 1500,
        "pClosing_C": 1490,
        "priceYesterday_C": 1450,
        "pMeDem_C": 1480,
        "qTitMeDem_C": 50,
        "pMeOf_C": 1520,
        "qTitMeOf_C": 70,
        "qTotTran5J_C": 1200,
        "qTotCap_C": 1.8e9,
        "zTotTran_C": 80,
        "oP_C": 5000,
        "yesterdayOP_C": 4800,
        # put side: nothing quoted yet, TSETMC sends zeros
        "insCode_P": "P1",
        "lVal18AFC_P": "طهرم2400",
        "lVal30_P": "اختيارف اهرم-24000-1405/08/14",
        "pDrCotVal_P": 0,
        "pClosing_P": 0,
        "priceYesterday_P": 0,
        "pMeDem_P": 0,
        "qTitMeDem_P": 0,
        "pMeOf_P": 0,
        "qTitMeOf_P": 0,
        "qTotTran5J_P": 0,
        "qTotCap_P": 0,
        "zTotTran_P": 0,
        "oP_P": 0,
        "yesterdayOP_P": 0,
    }
    row.update(overrides)
    return row


def parse(*rows, today=TODAY):
    fetched = datetime(2026, 10, 17, 11, 0, tzinfo=TEHRAN_TZ)
    return parse_market_watch({"instrumentOptMarketWatch": list(rows)}, fetched_at=fetched, today=today)


# -- row layout -------------------------------------------------------------------
def test_call_and_put_are_split_from_one_row():
    snapshot = parse(make_row())
    assert [q.option_type for q in snapshot.options] == ["call", "put"]

    underlying = snapshot.underlyings["UA1"]
    assert (underlying.symbol, underlying.last, underlying.close, underlying.yesterday) == ("اهرم", 24000, 23900, 23800)

    call, put = snapshot.options
    assert call.ins_code == "C1" and call.symbol == "ضهرم2400"
    assert call.strike == 24000 and call.expiry == date(2026, 11, 5) and call.contract_size == 1000
    assert (call.last, call.close, call.bid, call.ask) == (1500, 1490, 1480, 1520)
    assert (call.bid_volume, call.ask_volume, call.volume, call.trades) == (50, 70, 1200, 80)
    assert (call.open_interest, call.prev_open_interest) == (5000, 4800)
    assert call.value == pytest.approx(1.8e9)


def test_zero_means_no_value_for_prices_but_not_for_volumes():
    put = parse(make_row()).options[1]
    assert put.last is None and put.close is None and put.bid is None and put.ask is None
    assert put.volume == 0 and put.open_interest == 0


def test_malformed_rows_are_skipped_not_fatal():
    good = make_row()
    snapshot = parse({"uaInsCode": "X"}, make_row(strikePrice=0), "not a dict", good)
    assert len(snapshot.options) == 2  # only the good row survived


def test_arabic_letters_are_normalised():
    assert _clean_text("\u064a\u0643 ") == "\u06cc\u06a9"


# -- expiry resolution ----------------------------------------------------------------
def test_expiry_falls_back_to_jalali_date_in_the_name():
    snapshot = parse(make_row(endDate="garbage"))
    assert snapshot.options[0].expiry == date(2026, 11, 5)  # 1405/08/14


def test_expiry_falls_back_to_remained_days():
    row = make_row(endDate=None, lVal30_C="no date here", lVal30_P="no date here", remainedDay=10)
    assert parse(row).options[0].expiry == TODAY + timedelta(days=10)


def test_row_without_any_expiry_information_is_skipped():
    row = make_row(endDate=None, lVal30_C="x", lVal30_P="x", remainedDay=None)
    assert parse(row).options == []


@pytest.mark.parametrize(
    "raw",
    [20261105, "20261105", "2026-11-05", "2026-11-05T00:00:00", "2026/11/05", "۱۴۰۵/۰۸/۱۴", "1405/8/14"],
)
def test_parse_date_accepts_common_formats(raw):
    assert parse_date(raw) == date(2026, 11, 5)


@pytest.mark.parametrize("raw", [None, "", 0, "garbage", "20261340"])
def test_parse_date_rejects_garbage(raw):
    assert parse_date(raw) is None


# -- Jalali conversion --------------------------------------------------------------
@pytest.mark.parametrize(
    "jalali,gregorian",
    [
        ((1403, 8, 30), date(2024, 11, 20)),
        ((1405, 7, 25), date(2026, 10, 17)),
        ((1404, 1, 1), date(2025, 3, 21)),
        ((1399, 12, 30), date(2021, 3, 20)),  # 30 Esfand of a leap year
    ],
)
def test_known_jalali_dates(jalali, gregorian):
    assert jalali_to_gregorian(*jalali) == gregorian


def test_matches_jdatetime_for_every_day_in_25_years():
    jdatetime = pytest.importorskip("jdatetime")
    day = date(2015, 1, 1)
    while day <= date(2040, 12, 31):
        j = jdatetime.date.fromgregorian(date=day)
        assert jalali_to_gregorian(j.year, j.month, j.day) == day
        day += timedelta(days=1)
