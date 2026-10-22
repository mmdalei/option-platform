"use client";

import { useRouter, useSearchParams } from "next/navigation";
import Change from "@/components/Change";
import Notice from "@/components/Notice";
import OptionChainTable from "@/components/OptionChainTable";
import { POLL_MS, useOptionChain, useUnderlyings, type LiveStatus } from "@/hooks/useOptionChain";
import { cn } from "@/lib/cn";
import { fmtClock, fmtDays, fmtInt, fmtJalali } from "@/lib/format";

const STATUS_TEXT: Record<LiveStatus, string> = {
  connecting: "در حال اتصال…",
  live: "زنده",
  polling: `به‌روزرسانی هر ${fmtInt(POLL_MS / 1000)} ثانیه`,
};

export default function OptionChainView() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: underlyings, error: listError } = useUnderlyings();

  // The URL is the state (shareable, survives reload); unknown values fall back to the first item.
  const selected = underlyings?.find((u) => u.ins_code === params.get("underlying")) ?? underlyings?.[0] ?? null;
  const expiry =
    selected?.expiries.find((e) => e.date === params.get("expiry"))?.date ?? selected?.expiries[0]?.date ?? null;

  const { data, status, error } = useOptionChain(selected?.ins_code ?? null, expiry);

  const choose = (next: { underlying: string; expiry?: string }) => {
    const query = new URLSearchParams({ underlying: next.underlying });
    if (next.expiry) query.set("expiry", next.expiry);
    router.replace(`/option-chain?${query.toString()}`, { scroll: false });
  };

  if (!underlyings) {
    return listError ? <Notice tone="error">{listError}</Notice> : <div className="h-24 rounded-md bg-panel" aria-busy="true" />;
  }
  if (!selected) {
    return <Notice tone="info">هنوز دارایی پایه‌ای با اختیار معامله ثبت نشده است.</Notice>;
  }

  // Prefer the live numbers that come with the chain over the slower list refresh.
  const quote = data?.underlying ?? selected;
  const offline = Boolean(error) && status !== "live";

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-6">
          <label className="block">
            <span className="mb-1 block text-[12px] text-ink-soft">دارایی پایه</span>
            <select
              value={selected.ins_code}
              onChange={(e) => choose({ underlying: e.target.value })}
              className="h-10 min-w-44 rounded-md border border-rule bg-panel px-3 text-[15px] font-semibold"
            >
              {underlyings.map((u) => (
                <option key={u.ins_code} value={u.ins_code}>
                  {u.symbol}
                </option>
              ))}
            </select>
          </label>

          <div>
            <span className="mb-1 block text-[12px] text-ink-soft">قیمت دارایی پایه (ریال)</span>
            <p className="flex h-10 items-center gap-3 text-[20px] font-bold tabular-nums">
              {fmtInt(quote.price)}
              <span className="text-[13px] font-normal">
                <Change value={quote.change_pct} />
              </span>
            </p>
          </div>
        </div>

        <p className="flex items-center gap-2 text-[12px] text-ink-soft" role="status">
          <span
            aria-hidden
            className={cn(
              "h-2 w-2 rounded-full",
              offline ? "bg-down" : status === "live" ? "bg-up" : "bg-atm-strong",
            )}
          />
          {offline ? "قطع" : STATUS_TEXT[status]}
          {data && <span className="tabular-nums">آخرین به‌روزرسانی {fmtClock(data.updated_at)}</span>}
        </p>
      </div>

      <div role="group" aria-label="سررسید" className="flex flex-wrap gap-2">
        {selected.expiries.map((e) => (
          <button
            key={e.date}
            type="button"
            aria-pressed={e.date === expiry}
            onClick={() => choose({ underlying: selected.ins_code, expiry: e.date })}
            className={cn(
              "rounded-md border px-3 py-1.5 text-[13px]",
              e.date === expiry ? "border-ink bg-ink text-white" : "border-rule bg-panel hover:border-ink-soft",
            )}
          >
            <span className="font-semibold tabular-nums">{fmtJalali(e.date)}</span>
            <span className="ms-2 text-[12px] opacity-80">{fmtDays(e.days)}</span>
          </button>
        ))}
      </div>

      <OptionChainTable data={data} error={error} />
    </section>
  );
}
