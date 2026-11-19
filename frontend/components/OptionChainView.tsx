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
    return listError ? (
      <Notice tone="error">{listError}</Notice>
    ) : (
      <div className="space-y-4" aria-busy="true">
        <div className="h-24 rounded-lg border border-rule bg-panel p-4 shadow-xs">
          <div className="h-full rounded-md bg-ledger motion-safe:animate-pulse" />
        </div>
        <div className="flex gap-2">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="h-10 w-32 rounded-md border border-rule bg-panel motion-safe:animate-pulse" />
          ))}
        </div>
      </div>
    );
  }
  if (!selected) {
    return <Notice tone="info">هنوز دارایی پایه‌ای با اختیار معامله ثبت نشده است.</Notice>;
  }

  // Prefer the live numbers that come with the chain over the slower list refresh.
  const quote = data?.underlying ?? selected;
  const offline = Boolean(error) && status !== "live";

  return (
    <section className="space-y-5">
      <div className="rounded-lg border border-rule bg-panel p-4 shadow-xs">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">دارایی پایه</span>
              <select
                value={selected.ins_code}
                onChange={(e) => choose({ underlying: e.target.value })}
                className="h-10 min-w-[12rem] rounded-md border border-rule-strong bg-panel px-3 text-[15px] font-semibold text-ink transition-colors duration-150 hover:border-ink-soft"
              >
                {underlyings.map((u) => (
                  <option key={u.ins_code} value={u.ins_code}>
                    {u.symbol}
                  </option>
                ))}
              </select>
            </label>

            <div>
              <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">قیمت دارایی پایه (ریال)</span>
              <p className="flex min-h-10 items-center gap-3 text-[20px] font-bold leading-none tabular-nums text-ink">
                {fmtInt(quote.price)}
                <span className="text-[13px] font-medium">
                  <Change value={quote.change_pct} />
                </span>
              </p>
            </div>
          </div>

          <p
            className="inline-flex min-h-10 flex-wrap items-center gap-2.5 rounded-md border border-rule bg-paper px-3 py-1.5 text-[12px] text-ink-soft"
            role="status"
          >
            <span className="inline-flex items-center gap-2">
              <span
                aria-hidden
                className={cn(
                  "h-2 w-2 shrink-0 rounded-full",
                  offline ? "bg-down" : status === "live" ? "bg-up" : "bg-warn",
                )}
              />
              <span className={cn("font-medium", offline ? "text-down" : status === "live" ? "text-up" : "text-ink")}>
                {offline ? "قطع" : STATUS_TEXT[status]}
              </span>
            </span>
            {data && (
              <span className="border-s border-rule ps-2.5 tabular-nums text-ink-soft">
                آخرین به‌روزرسانی {fmtClock(data.updated_at)}
              </span>
            )}
          </p>
        </div>
      </div>

      <div role="group" aria-label="سررسید" className="flex flex-wrap items-center gap-2">
        {selected.expiries.map((e) => (
          <button
            key={e.date}
            type="button"
            aria-pressed={e.date === expiry}
            onClick={() => choose({ underlying: selected.ins_code, expiry: e.date })}
            className={cn(
              "inline-flex min-h-10 items-center rounded-md border px-3.5 py-2 text-[13px] transition-colors duration-150",
              e.date === expiry
                ? "border-ink bg-ink text-white shadow-xs hover:bg-ink/90 focus-visible:outline-focus-on-dark"
                : "border-rule-strong bg-panel text-ink hover:border-ink-soft hover:bg-ledger active:bg-rule/40",
            )}
          >
            <span className="font-semibold tabular-nums">{fmtJalali(e.date)}</span>
            <span className={cn("ms-2 text-[12px]", e.date === expiry ? "text-ink-on-dark-soft" : "text-ink-soft")}>
              {fmtDays(e.days)}
            </span>
          </button>
        ))}
      </div>

      <OptionChainTable data={data} error={error} />
    </section>
  );
}