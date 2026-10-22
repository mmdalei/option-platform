"""
probe_tsetmc.py - read-only probe of the live TSETMC option endpoint (milestone M0).

What it does
    1. Calls the endpoint once (optionally a second time after --again seconds).
    2. Saves the raw response untouched to backend/samples/.
    3. Prints and saves a text report: field inventory, unknown fields, parser dry-run,
       data-quality counts, value-unit evidence, underlyings (focus symbol), and what
       changed between the two fetches.

It never writes to the database, never changes existing files and never sends orders.
It only REPORTS what it sees: interpretation is left to the reader.

Run from the backend folder:
    python tools/probe_tsetmc.py --focus اهرم --again 15
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from tsetmc_collector import TEHRAN_TZ, _HEADERS, _clean_text, _parse_row, parse_date, tehran_today  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROWS_KEY = "instrumentOptMarketWatch"
NAME_UA = ("lval30_UA", "lVal30_UA", "lVal18AFC_UA")
BASE = {
    "contractSize", "uaInsCode", "strikePrice", "endDate", "remainedDay",
    "pDrCotVal_UA", "pClosing_UA", "priceYesterday_UA",
}
SIDE = (
    "insCode", "lVal18AFC", "lVal30", "pDrCotVal", "pClosing", "priceYesterday",
    "pMeDem", "qTitMeDem", "pMeOf", "qTitMeOf", "qTotTran5J", "qTotCap",
    "zTotTran", "oP", "yesterdayOP",
)
EXPECTED = BASE | set(NAME_UA) | {f"{name}_{s}" for name in SIDE for s in "CP"}
ZERO_WATCH = ("pDrCotVal", "pMeDem", "pMeOf", "qTotTran5J", "oP")
TIME_NAME = re.compile(r"(time|date|even|hour|tim|dt)", re.IGNORECASE)
TIME_VALUE = re.compile(r"^(\d{6}|\d{8}|\d{4}[-/]\d{1,2}[-/]\d{1,2}.*|\d{1,2}:\d{2}.*)$")


def num(value):
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def fetch(url: str, timeout: float):
    started = time.monotonic()
    with httpx.Client(timeout=timeout, headers=_HEADERS, follow_redirects=True) as client:
        response = client.get(url)
    return response, time.monotonic() - started


def get_rows(payload) -> list:
    if isinstance(payload, dict) and isinstance(payload.get(ROWS_KEY), list):
        return payload[ROWS_KEY]
    return []


def snapshot_map(rows) -> tuple[dict, dict]:
    options, underlyings = {}, {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("uaInsCode") is not None:
            underlyings[str(row["uaInsCode"])] = row.get("pDrCotVal_UA")
        for s in "CP":
            code = row.get(f"insCode_{s}")
            if code:
                options[str(code)] = tuple(
                    row.get(f"{name}_{s}") for name in ("pDrCotVal", "pMeDem", "pMeOf", "qTotTran5J", "oP")
                )
    return options, underlyings


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only probe of the TSETMC option endpoint")
    ap.add_argument("--market", type=int, default=settings.tsetmc_market, help="0 both, 1 Bourse, 2 FaraBourse")
    ap.add_argument("--focus", default="اهرم", help="text to look for in underlying names")
    ap.add_argument("--again", type=float, default=0.0, help="fetch a second time after N seconds and compare")
    ap.add_argument("--timeout", type=float, default=settings.request_timeout)
    ap.add_argument("--out", default=str(BACKEND / "samples"))
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines: list[str] = []

    def out(text: str = "") -> None:
        print(text)
        lines.append(text)

    def save_report() -> Path:
        path = out_dir / f"tsetmc_probe_{stamp}.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    url = f"{settings.tsetmc_base_url}/api/Instrument/GetInstrumentOptionMarketWatch/{args.market}"

    # -- 1. connection ---------------------------------------------------------------
    out("== 1. اتصال ==")
    out(f"url: {url}")
    try:
        response, elapsed = fetch(url, args.timeout)
    except httpx.HTTPError as exc:
        out(f"FAILED: {exc!r}")
        out(f"report: {save_report()}")
        return 1
    out(f"status: {response.status_code}   elapsed: {elapsed:.2f}s   bytes: {len(response.content)}")
    out(f"content-type: {response.headers.get('content-type')}")
    out(f"server Date header: {response.headers.get('date')}")
    out(f"Tehran now (local clock): {datetime.now(TEHRAN_TZ).isoformat(timespec='seconds')}")

    raw_path = out_dir / f"tsetmc_raw_{stamp}.json"
    raw_path.write_bytes(response.content)  # untouched, so it can serve as a test fixture
    out(f"raw saved: {raw_path}")
    if response.status_code != 200:
        out(f"body start: {response.text[:300]!r}")
        out(f"report: {save_report()}")
        return 1

    try:
        payload = response.json()
    except ValueError as exc:
        out(f"body is not JSON: {exc!r}; start: {response.text[:300]!r}")
        out(f"report: {save_report()}")
        return 1

    # -- 2. structure -----------------------------------------------------------------
    out("\n== 2. ساختار ==")
    out(f"top-level type: {type(payload).__name__}")
    if isinstance(payload, dict):
        out(f"top-level keys: {sorted(payload)}")
    rows = get_rows(payload)
    dict_rows = [r for r in rows if isinstance(r, dict)]
    out(f"rows under '{ROWS_KEY}': {len(rows)} (dict rows: {len(dict_rows)})")
    if not dict_rows:
        out("no usable rows: nothing more to report")
        out(f"report: {save_report()}")
        return 1
    n = len(dict_rows)

    # -- 3. field inventory ---------------------------------------------------------
    stats: dict[str, dict] = {}
    for row in dict_rows:
        for key, value in row.items():
            s = stats.setdefault(key, {"present": 0, "none": 0, "zero": 0, "types": Counter(), "example": None})
            s["present"] += 1
            s["types"][type(value).__name__] += 1
            if value is None:
                s["none"] += 1
            elif num(value) == 0 and not isinstance(value, bool):
                s["zero"] += 1
            elif s["example"] is None and value != "":
                s["example"] = value

    out("\n== 3. فیلدها ==")
    absent = sorted(k for k in EXPECTED if k not in stats and k not in NAME_UA)
    out(f"expected but ABSENT in every row ({len(absent)}): {absent}")
    out(f"underlying-name fields present: {[k for k in NAME_UA if k in stats]}")
    unknown = sorted(k for k in stats if k not in EXPECTED)
    out(f"\nunknown fields (not used by the parser) ({len(unknown)}):")
    for key in unknown:
        s = stats[key]
        example = str(s["example"])[:60]
        hint = ""
        if TIME_NAME.search(key) or TIME_VALUE.match(str(s["example"] or "")):
            hint = "   <-- possible date/time (heuristic only)"
        out(f"  {key}: present {s['present']}/{n}, null {s['none']}, zero {s['zero']}, "
            f"types {dict(s['types'])}, example {example!r}{hint}")
    out("\nexpected fields that are missing in some rows or contain null:")
    shown = 0
    for key in sorted(k for k in EXPECTED if k in stats):
        s = stats[key]
        if s["present"] < n or s["none"] > 0:
            out(f"  {key}: present {s['present']}/{n}, null {s['none']}, types {dict(s['types'])}")
            shown += 1
    if not shown:
        out("  (none)")
    out("\nzero ratio of key numeric fields (TSETMC uses 0 for 'no value'):")
    for name in ZERO_WATCH:
        for side in "CP":
            s = stats.get(f"{name}_{side}")
            if s:
                out(f"  {name}_{side}: zero {s['zero']}/{s['present']} = {s['zero'] / s['present']:.0%}")

    # -- 4. parser dry-run ------------------------------------------------------------
    out("\n== 4. اجرای آزمایشی پارسر فعلی ==")
    today = tehran_today()
    parsed = 0
    errors: Counter = Counter()
    for row in dict_rows:
        try:
            _parse_row(row, today)
            parsed += 1
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            errors[f"{type(exc).__name__}: {exc}"] += 1
    out(f"rows parsed: {parsed}/{n}   skipped: {n - parsed}")
    for message, count in errors.most_common(5):
        out(f"  skipped x{count}: {message}")
    direct = sum(parse_date(r.get("endDate")) is not None for r in dict_rows)
    out(f"endDate parsed directly: {direct}/{n} (the rest rely on name/remainedDay fallbacks = guesses)")
    out(f"contractSize present: {sum(r.get('contractSize') not in (None, '', 0) for r in dict_rows)}/{n}; "
        f"values: {dict(Counter(r.get('contractSize') for r in dict_rows))}")
    past = sum((d := parse_date(r.get("endDate"))) is not None and d < today for r in dict_rows)
    out(f"rows with expiry before today: {past}")

    # -- 5. quality counts --------------------------------------------------------------
    out("\n== 5. کیفیت داده ==")
    triple = Counter((r.get("uaInsCode"), r.get("strikePrice"), str(r.get("endDate"))) for r in dict_rows)
    dup_triple = {k: v for k, v in triple.items() if v > 1}
    out(f"duplicate (underlying, strike, endDate) rows: {len(dup_triple)}")
    for key, count in list(dup_triple.items())[:3]:
        out(f"  {key} x{count}")
    for side in "CP":
        codes = Counter(r.get(f"insCode_{side}") for r in dict_rows if r.get(f"insCode_{side}"))
        out(f"duplicate insCode_{side}: {sum(v > 1 for v in codes.values())}   "
            f"rows without insCode_{side}: {sum(not r.get(f'insCode_{side}') for r in dict_rows)}")
        crossed = negative = 0
        for r in dict_rows:
            bid, ask = num(r.get(f"pMeDem_{side}")), num(r.get(f"pMeOf_{side}"))
            if bid and ask and bid > ask:
                crossed += 1
            if any((num(r.get(f"{f}_{side}")) or 0) < 0 for f in ("qTotTran5J", "oP", "qTotCap")):
                negative += 1
        out(f"  bid > ask (both > 0): {crossed}   negative volume/OI/value: {negative}")

    # -- 6. value unit evidence -------------------------------------------------------
    out("\n== 6. شاهد واحد qTotCap (ارزش معاملات) ==")
    ratios, ratios_per_size = [], []
    for r in dict_rows:
        size = num(r.get("contractSize")) or 1000
        for side in "CP":
            vol, last, cap = num(r.get(f"qTotTran5J_{side}")), num(r.get(f"pDrCotVal_{side}")), num(r.get(f"qTotCap_{side}"))
            if vol and last and cap and vol > 0 and last > 0 and cap > 0:
                ratios.append(cap / (vol * last))
                ratios_per_size.append(cap / (vol * last * size))
    if ratios:
        out(f"contracts with volume, last price and value: {len(ratios)}")
        out(f"median qTotCap / (volume x last): {statistics.median(ratios):.4g}   "
            f"min {min(ratios):.4g}   max {max(ratios):.4g}")
        out(f"median qTotCap / (volume x last x contractSize): {statistics.median(ratios_per_size):.4g}")
    else:
        out("no contract with volume, last price and value at the same time (market closed or no trades?)")

    # -- 7. underlyings -------------------------------------------------------------------
    out("\n== 7. دارایی‌های پایه ==")
    by_ua: dict[str, list[dict]] = {}
    for r in dict_rows:
        by_ua.setdefault(str(r.get("uaInsCode")), []).append(r)
    out(f"distinct underlyings: {len(by_ua)}")
    focus = _clean_text(args.focus)
    focus_rows: list[dict] = []
    for code, group in sorted(by_ua.items(), key=lambda kv: -len(kv[1])):
        first = group[0]
        names = {k: _clean_text(first.get(k)) for k in NAME_UA if k in first}
        expiries = sorted({str(r.get("endDate")) for r in group})
        is_focus = bool(focus) and any(focus in _clean_text(r.get(k)) for r in group for k in NAME_UA)
        if is_focus:
            focus_rows.extend(group)
        out(f"  {'*' if is_focus else ' '} {code}  rows {len(group)}  names {names}  "
            f"price {first.get('pDrCotVal_UA')}/{first.get('pClosing_UA')}/{first.get('priceYesterday_UA')}  "
            f"expiries {expiries[:6]}")
    out(f"(* = name contains {args.focus!r}; price = last/close/yesterday)")
    if focus_rows:
        focus_path = out_dir / f"tsetmc_focus_{stamp}.json"
        focus_path.write_text(json.dumps(focus_rows[:5], ensure_ascii=False, indent=2), encoding="utf-8")
        out(f"first {min(5, len(focus_rows))} raw rows of the focus symbol: {focus_path}")
    else:
        out(f"no underlying matched {args.focus!r}")

    # -- 8. second fetch ---------------------------------------------------------------
    if args.again > 0:
        out(f"\n== 8. تغییر بین دو دریافت (فاصله {args.again:g} ثانیه) ==")
        time.sleep(args.again)
        try:
            second, _ = fetch(url, args.timeout)
            second.raise_for_status()
            second_rows = get_rows(second.json())
        except (httpx.HTTPError, ValueError) as exc:
            out(f"second fetch FAILED: {exc!r}")
        else:
            before_o, before_u = snapshot_map(dict_rows)
            after_o, after_u = snapshot_map(second_rows)
            common = before_o.keys() & after_o.keys()
            changed = sum(before_o[k] != after_o[k] for k in common)
            volume_down = sum((num(after_o[k][3]) or 0) < (num(before_o[k][3]) or 0) for k in common)
            ua_changed = sum(before_u[k] != after_u[k] for k in before_u.keys() & after_u.keys())
            out(f"server Date header (2nd): {second.headers.get('date')}")
            out(f"contracts in both: {len(common)}   changed (last/bid/ask/volume/OI): {changed}   "
                f"volume decreased: {volume_down}")
            out(f"underlyings with changed last price: {ua_changed}/{len(before_u.keys() & after_u.keys())}")

    out(f"\nreport: {save_report()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())