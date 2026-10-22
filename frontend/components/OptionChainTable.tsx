"use client";

import { Fragment, useState, type ReactNode } from "react";
import type { ChainResponse, ChainRow, Moneyness, OptionLeg, UnderlyingQuote } from "@/lib/api";
import { cn } from "@/lib/cn";
import { DASH, fmtDecimal, fmtInt, fmtPercent } from "@/lib/format";
import Change from "./Change";
import Notice from "./Notice";

type ViewMode = "basic" | "greeks";

interface Column {
  key: string;
  label: string;
  /** Header tooltip: what the column means. */
  hint: string;
  /** Only shown in the "greeks" view. */
  greeksOnly?: boolean;
  render: (leg: OptionLeg) => ReactNode;
  /** Cell tooltip with extra detail for that one contract. */
  title?: (leg: OptionLeg) => string | undefined;
}

const PRICE_SOURCE_LABEL = { mid: "میانگین خرید و فروش", last: "آخرین معامله", close: "قیمت پایانی" } as const;

/**
 * Columns of the CALL side, listed from the outer edge of the table towards the strike.
 * The PUT side uses the same list reversed, so the two sides mirror each other and the
 * prices (the columns you read first) sit next to the strike in the middle.
 */
const COLUMNS: Column[] = [
  { key: "symbol", label: "نماد", hint: "نماد قرارداد", greeksOnly: true, render: (l) => l.symbol },
  {
    key: "oi",
    label: "موقعیت باز",
    hint: "موقعیت‌های باز (Open Interest)",
    render: (l) => fmtInt(l.open_interest),
    title: (l) => (l.oi_change == null ? undefined : `تغییر نسبت به دیروز: ${fmtInt(l.oi_change)}`),
  },
  { key: "volume", label: "حجم", hint: "حجم معاملات امروز (قرارداد)", render: (l) => fmtInt(l.volume) },
  {
    key: "vega",
    label: "وگا",
    hint: "تغییر قیمت اختیار (ریال) به ازای یک واحد درصد تغییر نوسان",
    greeksOnly: true,
    render: (l) => fmtDecimal(l.vega, 1),
  },
  {
    key: "theta",
    label: "تتا",
    hint: "تغییر قیمت اختیار (ریال) با گذشت یک روز",
    greeksOnly: true,
    render: (l) => fmtDecimal(l.theta, 1),
  },
  {
    key: "gamma",
    label: "گاما",
    hint: "تغییر دلتا به ازای یک ریال تغییر قیمت دارایی پایه",
    greeksOnly: true,
    render: (l) => fmtDecimal(l.gamma, 6),
  },
  {
    key: "delta",
    label: "دلتا",
    hint: "تغییر قیمت اختیار (ریال) به ازای یک ریال تغییر قیمت دارایی پایه",
    render: (l) => fmtDecimal(l.delta, 2),
  },
  {
    key: "iv",
    label: "IV",
    hint: "نوسان ضمنی سالانه (Implied Volatility)",
    render: (l) => fmtPercent(l.iv, 1),
    title: (l) =>
      l.price_source ? `محاسبه‌شده از ${PRICE_SOURCE_LABEL[l.price_source]}: ${fmtInt(l.price_used)} ریال` : undefined,
  },
  {
    key: "bid",
    label: "خرید",
    hint: "بهترین قیمت سفارش خرید",
    render: (l) => fmtInt(l.bid),
    title: (l) => (l.bid_volume ? `حجم صف: ${fmtInt(l.bid_volume)}` : undefined),
  },
  {
    key: "ask",
    label: "فروش",
    hint: "بهترین قیمت سفارش فروش",
    render: (l) => fmtInt(l.ask),
    title: (l) => (l.ask_volume ? `حجم صف: ${fmtInt(l.ask_volume)}` : undefined),
  },
  {
    key: "chg",
    label: "تغییر",
    hint: "درصد تغییر آخرین قیمت نسبت به دیروز",
    render: (l) => <Change value={l.change_pct} />,
  },
  {
    key: "last",
    label: "آخرین",
    hint: "آخرین قیمت معامله (ریال)",
    render: (l) => <span className="font-semibold">{fmtInt(l.last)}</span>,
    title: (l) => l.symbol,
  },
];

/** Background of a cell by moneyness: in profit / at the money / in loss. */
const TINT: Record<Moneyness, string> = { ITM: "bg-itm", ATM: "bg-atm", OTM: "bg-otm" };

interface Props {
  /** The chain to show; null while loading. */
  data: ChainResponse | null;
  /** Latest error message. Without data it replaces the table, with data it becomes a warning. */
  error?: string | null;
}

export default function OptionChainTable({ data, error = null }: Props) {
  const [mode, setMode] = useState<ViewMode>("basic");

  if (!data) {
    return error ? <Notice tone="error">{error}</Notice> : <Skeleton />;
  }
  if (data.rows.length === 0) {
    return <Notice tone="info">برای این سررسید قراردادی پیدا نشد.</Notice>;
  }

  const columns = COLUMNS.filter((c) => mode === "greeks" || !c.greeksOnly);
  const callColumns = columns;
  const putColumns = [...columns].reverse();
  const colSpan = columns.length * 2 + 1;

  // The band with the underlying price goes between the two strikes that surround it.
  const spot = data.underlying.price;
  const spotIndex =
    spot == null
      ? -1
      : (() => {
          const i = data.rows.findIndex((row) => row.strike > spot);
          return i === -1 ? data.rows.length : i;
        })();

  const riskFree = Number(data.params.risk_free_rate);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Legend />
        <ModeToggle mode={mode} onChange={setMode} />
      </div>

      {error && (
        <Notice tone="warn">ارتباط برقرار نیست؛ آخرین داده دریافت‌شده نمایش داده می‌شود. ({error})</Notice>
      )}

      <div
        role="region"
        aria-label="جدول زنجیره قراردادها"
        tabIndex={0}
        className="max-h-[72vh] overflow-auto rounded-md border border-rule bg-panel"
      >
        <table className="w-full border-separate border-spacing-0 text-[13px]">
          <caption className="sr-only">
            زنجیره اختیار معامله {data.underlying.symbol}؛ اختیار خرید در سمت راست و اختیار فروش در سمت چپ قیمت اعمال
          </caption>
          <thead>
            <tr>
              <th
                colSpan={callColumns.length}
                className="sticky top-0 z-20 h-9 border-b border-rule bg-panel px-2 text-center font-bold"
              >
                اختیار خرید (Call)
              </th>
              <th
                rowSpan={2}
                scope="col"
                className="sticky top-0 z-20 border-x border-b border-rule bg-panel px-3 text-center font-bold"
              >
                قیمت اعمال
              </th>
              <th
                colSpan={putColumns.length}
                className="sticky top-0 z-20 h-9 border-b border-rule bg-panel px-2 text-center font-bold"
              >
                اختیار فروش (Put)
              </th>
            </tr>
            <tr>
              {callColumns.map((c) => (
                <HeaderCell key={`call-${c.key}`} column={c} />
              ))}
              {putColumns.map((c) => (
                <HeaderCell key={`put-${c.key}`} column={c} />
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <Fragment key={row.strike}>
                {i === spotIndex && <SpotRow underlying={data.underlying} colSpan={colSpan} />}
                <ChainTr row={row} callColumns={callColumns} putColumns={putColumns} />
              </Fragment>
            ))}
            {spotIndex === data.rows.length && <SpotRow underlying={data.underlying} colSpan={colSpan} />}
          </tbody>
        </table>
      </div>

      <p className="text-[12px] leading-6 text-ink-soft">
        قیمت‌ها به ریال و برای هر سهم‌اند؛ اندازه هر قرارداد {fmtInt(data.contract_size)} سهم است. نوسان ضمنی و یونانی‌ها
        با مدل بلک‌شولز و نرخ بدون ریسک {fmtPercent(riskFree, 0)} محاسبه شده‌اند.
      </p>
    </div>
  );
}

function HeaderCell({ column }: { column: Column }) {
  return (
    <th
      scope="col"
      title={column.hint}
      className="sticky top-9 z-20 h-8 whitespace-nowrap border-b border-rule bg-panel px-2 text-center text-[12px] font-medium text-ink-soft"
    >
      {column.label}
    </th>
  );
}

function ChainTr({
  row,
  callColumns,
  putColumns,
}: {
  row: ChainRow;
  callColumns: Column[];
  putColumns: Column[];
}) {
  return (
    <tr>
      <SideCells leg={row.call} columns={callColumns} side="call" />
      <th
        scope="row"
        className={cn(
          "border-x border-b border-rule px-3 py-1.5 text-center font-bold tabular-nums",
          row.is_atm ? "bg-atm-strong" : "bg-panel",
        )}
      >
        {fmtInt(row.strike)}
        {row.is_atm && <span className="block text-[10px] font-medium leading-3 text-ink-soft">سر به سر</span>}
      </th>
      <SideCells leg={row.put} columns={putColumns} side="put" />
    </tr>
  );
}

/** All cells of one side. A strike can exist for only one side, then a single dash fills the gap. */
function SideCells({ leg, columns, side }: { leg: OptionLeg | null; columns: Column[]; side: "call" | "put" }) {
  if (!leg) {
    return (
      <td colSpan={columns.length} className="border-b border-rule/60 px-2 py-1.5 text-center text-ink-soft">
        {DASH}
      </td>
    );
  }
  return (
    <>
      {columns.map((column) => (
        <td
          key={`${side}-${column.key}`}
          title={column.title?.(leg)}
          className={cn(
            "whitespace-nowrap border-b border-rule/60 px-2 py-1.5 text-center tabular-nums",
            leg.moneyness && TINT[leg.moneyness],
          )}
        >
          {column.render(leg)}
        </td>
      ))}
    </>
  );
}

/** Dark band that shows where the underlying trades relative to the strikes. */
function SpotRow({ underlying, colSpan }: { underlying: UnderlyingQuote; colSpan: number }) {
  return (
    <tr aria-label="قیمت فعلی دارایی پایه">
      <td colSpan={colSpan} className="bg-ink px-3 py-1.5 text-center text-white">
        <span className="font-bold">{underlying.symbol}</span>
        <span className="mx-4 tabular-nums">{fmtInt(underlying.price)} ریال</span>
        <Change value={underlying.change_pct} onDark />
      </td>
    </tr>
  );
}

function Legend() {
  const items = [
    { label: "در سود (ITM)", swatch: "bg-itm ring-itm-strong" },
    { label: "سر به سر (ATM)", swatch: "bg-atm ring-atm-strong" },
    { label: "در زیان (OTM)", swatch: "bg-otm ring-otm-strong" },
  ];
  return (
    <ul className="flex flex-wrap items-center gap-4 text-[12px] text-ink-soft" aria-label="راهنمای رنگ‌ها">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span aria-hidden className={cn("inline-block h-3 w-5 rounded-sm ring-1 ring-inset", item.swatch)} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

function ModeToggle({ mode, onChange }: { mode: ViewMode; onChange: (mode: ViewMode) => void }) {
  const options = [
    { value: "basic", label: "پایه" },
    { value: "greeks", label: "یونانی‌ها" },
  ] as const;
  return (
    <div
      role="group"
      aria-label="ستون‌های نمایش‌داده‌شده"
      className="inline-flex overflow-hidden rounded-md border border-rule bg-panel text-[13px]"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={mode === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "px-3.5 py-1.5",
            mode === option.value ? "bg-ink font-semibold text-white" : "text-ink-soft hover:text-ink",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="در حال بارگذاری" className="space-y-1 rounded-md border border-rule bg-panel p-2">
      {Array.from({ length: 9 }, (_, i) => (
        <div key={i} className="h-8 rounded-sm bg-paper motion-safe:animate-pulse" />
      ))}
    </div>
  );
}
