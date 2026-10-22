"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Notice from "@/components/Notice";
import PayoffChart from "@/components/PayoffChart";
import { useUnderlyings } from "@/hooks/useOptionChain";
import {
  describeError,
  postPayoff,
  type PayoffLegInput,
  type PayoffRequest,
  type PayoffResponse,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { DASH, fmtInt, parseNumber } from "@/lib/format";

type Kind = PayoffLegInput["kind"];
type Side = PayoffLegInput["side"];

/** One row of the editor. Every field holds the raw text the person typed. */
interface LegDraft {
  id: number;
  kind: Kind;
  side: Side;
  quantity: string;
  strike: string;
  price: string;
}

const CONTRACT_SIZE = 1000; // shares per option contract on the Tehran exchange

let idCounter = 0;
const draft = (kind: Kind, side: Side, quantity: number, strike: number | null, price: number): LegDraft => ({
  id: ++idCounter,
  kind,
  side,
  quantity: String(quantity),
  strike: strike === null ? "" : String(strike),
  price: String(price),
});

// -- presets ---------------------------------------------------------------------------
const unitFor = (spot: number) => (spot >= 10_000 ? 500 : spot >= 2_000 ? 100 : 50);
const atmStrike = (spot: number) => Math.round(spot / unitFor(spot)) * unitFor(spot);
const strikeStep = (spot: number) =>
  Math.max(unitFor(spot), Math.round((spot * 0.05) / unitFor(spot)) * unitFor(spot));

/** Rough premium that only pre-fills a preset so the chart is not empty: replace it with the real quote. */
function guessPremium(kind: "call" | "put", strike: number, spot: number): number {
  const intrinsic = kind === "call" ? Math.max(spot - strike, 0) : Math.max(strike - spot, 0);
  const timeValue = 0.05 * spot * Math.exp(-(((strike - spot) / (0.12 * spot)) ** 2));
  return Math.max(1, Math.round(intrinsic + timeValue));
}

const call = (side: Side, qty: number, strike: number, spot: number) =>
  draft("call", side, qty, strike, guessPremium("call", strike, spot));
const put = (side: Side, qty: number, strike: number, spot: number) =>
  draft("put", side, qty, strike, guessPremium("put", strike, spot));

const PRESETS: { label: string; build: (spot: number) => LegDraft[] }[] = [
  { label: "خرید اختیار خرید", build: (s) => [call("long", 1, atmStrike(s), s)] },
  { label: "خرید اختیار فروش", build: (s) => [put("long", 1, atmStrike(s), s)] },
  {
    label: "اسپرد صعودی",
    build: (s) => [call("long", 1, atmStrike(s) - strikeStep(s), s), call("short", 1, atmStrike(s) + strikeStep(s), s)],
  },
  {
    label: "کاورد کال",
    build: (s) => [draft("stock", "long", CONTRACT_SIZE, null, s), call("short", 1, atmStrike(s) + strikeStep(s), s)],
  },
  { label: "استرادل خرید", build: (s) => [call("long", 1, atmStrike(s), s), put("long", 1, atmStrike(s), s)] },
  {
    label: "باترفلای",
    build: (s) => [
      call("long", 1, atmStrike(s) - strikeStep(s), s),
      call("short", 2, atmStrike(s), s),
      call("long", 1, atmStrike(s) + strikeStep(s), s),
    ],
  },
];

// -- text -> request ---------------------------------------------------------------------
function buildRequest(spotText: string, drafts: LegDraft[]): { request: PayoffRequest | null; problem: string | null } {
  if (drafts.length === 0) return { request: null, problem: "حداقل یک ردیف اضافه کنید." };

  const legs: PayoffLegInput[] = [];
  for (const [index, d] of drafts.entries()) {
    const row = `ردیف ${fmtInt(index + 1)}`;
    const quantity = parseNumber(d.quantity);
    const price = parseNumber(d.price);
    const strike = d.kind === "stock" ? null : parseNumber(d.strike);
    if (quantity === null || quantity <= 0) return { request: null, problem: `${row}: تعداد را وارد کنید.` };
    if (price === null || price < 0) {
      return { request: null, problem: `${row}: ${d.kind === "stock" ? "قیمت ورود" : "پریمیوم"} را وارد کنید.` };
    }
    if (d.kind !== "stock" && (strike === null || strike <= 0)) {
      return { request: null, problem: `${row}: قیمت اعمال را وارد کنید.` };
    }
    legs.push({ kind: d.kind, side: d.side, quantity, price, strike, contract_size: CONTRACT_SIZE });
  }
  const spot = parseNumber(spotText);
  return { request: { legs, spot: spot !== null && spot > 0 ? spot : null }, problem: null };
}

const CONTROL =
  "h-10 w-full rounded-md border border-rule bg-panel px-2.5 text-[14px] tabular-nums disabled:bg-paper disabled:text-ink-soft";

const money = (value: number | null) => (value === null ? DASH : `${fmtInt(value)} ریال`);

export default function PayoffBuilder() {
  const { data: underlyings } = useUnderlyings(30_000);
  const [spotText, setSpotText] = useState("24000");
  const [legs, setLegs] = useState<LegDraft[]>(() => PRESETS[2].build(24_000));
  const [result, setResult] = useState<PayoffResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { request, problem } = useMemo(() => buildRequest(spotText, legs), [spotText, legs]);
  const requestKey = request ? JSON.stringify(request) : null;
  const spotValue = parseNumber(spotText);

  // Recompute 250 ms after the last edit; a newer edit cancels the request that is still running.
  useEffect(() => {
    if (!request) {
      setResult(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await postPayoff(request, controller.signal);
        if (controller.signal.aborted) return;
        setResult(response);
        setError(null);
      } catch (e) {
        if (!controller.signal.aborted) setError(describeError(e));
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // `request` is fully described by requestKey
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const update = (id: number, patch: Partial<LegDraft>) =>
    setLegs((current) => current.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const remove = (id: number) => setLegs((current) => current.filter((l) => l.id !== id));
  const add = () =>
    setLegs((current) => [...current, { id: ++idCounter, kind: "call", side: "long", quantity: "1", strike: "", price: "" }]);

  const spotIsValid = spotValue !== null && spotValue > 0;

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">ماشین‌حساب سود و زیان استراتژی</h1>
        <p className="mt-1 text-[14px] text-ink-soft">
          موقعیت‌ها را وارد کنید تا نمودار سود و زیان در روز سررسید رسم شود. همه مبالغ به ریال و هر قرارداد {fmtInt(CONTRACT_SIZE)} سهم است.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,27rem)_minmax(0,1fr)]">
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3">
            <Field label="قیمت فعلی دارایی پایه">
              <input
                className={CONTROL}
                inputMode="decimal"
                value={spotText}
                onChange={(e) => setSpotText(e.target.value)}
              />
            </Field>
            <Field label="پر کردن از بازار">
              <select
                className={CONTROL}
                value=""
                disabled={!underlyings?.length}
                onChange={(e) => {
                  const picked = underlyings?.find((u) => u.ins_code === e.target.value);
                  if (picked?.price) setSpotText(String(picked.price));
                }}
              >
                <option value="">{underlyings?.length ? "انتخاب نماد" : "بدون داده"}</option>
                {underlyings?.map((u) => (
                  <option key={u.ins_code} value={u.ins_code}>
                    {u.symbol}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div>
            <p className="mb-2 text-[12px] text-ink-soft">استراتژی‌های آماده (پریمیوم‌ها نمونه‌اند؛ با قیمت واقعی جایگزین کنید)</p>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  disabled={!spotIsValid}
                  onClick={() => spotValue && setLegs(preset.build(spotValue))}
                  className="rounded-md border border-rule bg-panel px-3 py-1.5 text-[13px] hover:border-ink-soft disabled:opacity-50"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <ul className="space-y-3" aria-label="موقعیت‌های استراتژی">
            {legs.map((l, index) => (
              <li key={l.id} className="rounded-md border border-rule bg-panel p-3">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="موقعیت">
                    <select className={CONTROL} value={l.side} onChange={(e) => update(l.id, { side: e.target.value as Side })}>
                      <option value="long">خرید</option>
                      <option value="short">فروش</option>
                    </select>
                  </Field>
                  <Field label="ابزار">
                    <select className={CONTROL} value={l.kind} onChange={(e) => update(l.id, { kind: e.target.value as Kind })}>
                      <option value="call">اختیار خرید</option>
                      <option value="put">اختیار فروش</option>
                      <option value="stock">سهم پایه</option>
                    </select>
                  </Field>
                  <Field label={l.kind === "stock" ? "تعداد سهم" : "تعداد قرارداد"}>
                    <input className={CONTROL} inputMode="decimal" value={l.quantity} onChange={(e) => update(l.id, { quantity: e.target.value })} />
                  </Field>
                  <Field label="قیمت اعمال">
                    <input
                      className={CONTROL}
                      inputMode="decimal"
                      value={l.kind === "stock" ? "" : l.strike}
                      disabled={l.kind === "stock"}
                      onChange={(e) => update(l.id, { strike: e.target.value })}
                    />
                  </Field>
                  <Field label={l.kind === "stock" ? "قیمت ورود" : "پریمیوم (هر سهم)"}>
                    <input className={CONTROL} inputMode="decimal" value={l.price} onChange={(e) => update(l.id, { price: e.target.value })} />
                  </Field>
                  <div className="flex items-end justify-end">
                    <button
                      type="button"
                      onClick={() => remove(l.id)}
                      aria-label={`حذف ردیف ${fmtInt(index + 1)}`}
                      className="h-10 rounded-md px-3 text-[13px] text-down hover:bg-otm"
                    >
                      حذف
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>

          <button
            type="button"
            onClick={add}
            disabled={legs.length >= 12}
            className="w-full rounded-md border border-dashed border-ink-soft py-2 text-[14px] hover:bg-panel disabled:opacity-50"
          >
            افزودن ردیف
          </button>
        </div>

        <div className="space-y-4">
          {problem && <Notice tone="info">{problem}</Notice>}
          {error && <Notice tone="error">{error}</Notice>}

          {result && request && (
            <>
              <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-rule bg-rule sm:grid-cols-4">
                <Stat
                  label="حداکثر سود"
                  value={result.profit_unbounded ? "نامحدود" : money(result.max_profit)}
                  tone="up"
                />
                <Stat
                  label="حداکثر زیان"
                  value={result.loss_unbounded ? "نامحدود" : money(result.max_loss)}
                  tone={result.max_loss !== null && result.max_loss >= 0 ? "up" : "down"}
                />
                <Stat
                  label="نقطه سر به سر"
                  value={result.break_evens.length ? result.break_evens.map((v) => fmtInt(v)).join("، ") : "ندارد"}
                />
                <Stat
                  label={result.net_premium < 0 ? "پرداختی اولیه (پریمیوم)" : "دریافتی اولیه (پریمیوم)"}
                  value={money(Math.abs(result.net_premium))}
                />
              </dl>

              <div className="rounded-md border border-rule bg-panel p-3">
                <PayoffChart x={result.x} y={result.y} spot={request.spot ?? null} breakEvens={result.break_evens} />
              </div>

              {result.pnl_at_spot !== null && (
                <p className="text-[13px] text-ink-soft">
                  اگر قیمت در سررسید برابر قیمت فعلی بماند:{" "}
                  <span className={cn("font-semibold tabular-nums", result.pnl_at_spot >= 0 ? "text-up" : "text-down")}>
                    {money(result.pnl_at_spot)}
                  </span>
                </p>
              )}
              <p className="text-[12px] text-ink-soft">کارمزد معاملات، مالیات و وجه تضمین در محاسبه لحاظ نشده است.</p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] text-ink-soft">{label}</span>
      {children}
    </label>
  );
}

function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "up" | "down" }) {
  return (
    <div className="bg-panel px-4 py-3">
      <dt className="text-[12px] text-ink-soft">{label}</dt>
      <dd className={cn("mt-1 text-[16px] font-bold tabular-nums", tone === "up" && "text-up", tone === "down" && "text-down")}>
        {value}
      </dd>
    </div>
  );
}
