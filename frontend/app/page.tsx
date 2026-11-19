"use client";

import Link from "next/link";
import Change from "@/components/Change";
import Notice from "@/components/Notice";
import { useUnderlyings } from "@/hooks/useOptionChain";
import { DASH, fmtDays, fmtDecimal, fmtInt, fmtJalali } from "@/lib/format";

const TH = "whitespace-nowrap border-b border-rule px-4 py-3 text-start font-semibold";
const TD = "whitespace-nowrap border-b border-rule/70 px-4 py-2 tabular-nums text-ink group-last:border-b-0";

export default function DashboardPage() {
  const { data, error } = useUnderlyings();

  return (
    <section className="space-y-6">
      <div className="border-b border-rule pb-4">
        <h1 className="text-[22px] font-bold leading-8 tracking-tight text-ink sm:text-[24px]">
          دارایی‌های پایه دارای اختیار معامله
        </h1>
        <p className="mt-1.5 text-[14px] leading-6 text-ink-soft">
          نمادها بر اساس ارزش معاملات اختیار امروز مرتب شده‌اند. برای دیدن زنجیره قراردادها روی نماد بزنید.
        </p>
      </div>

      {!data && error && <Notice tone="error">{error}</Notice>}
      {!data && !error && (
        <div aria-busy="true" className="overflow-hidden rounded-lg border border-rule bg-panel shadow-xs">
          <div className="h-11 border-b border-rule bg-ledger motion-safe:animate-pulse" />
          <div className="divide-y divide-rule/70 p-2">
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className="h-11 rounded-sm bg-paper motion-safe:animate-pulse" />
            ))}
          </div>
        </div>
      )}
      {data && data.length === 0 && <Notice tone="info">هنوز دارایی پایه‌ای با اختیار معامله ثبت نشده است.</Notice>}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-rule bg-panel shadow-xs">
          <table className="w-full border-separate border-spacing-0 text-[14px]">
            <caption className="sr-only">دارایی‌های پایه دارای اختیار معامله</caption>
            <thead className="bg-ledger text-[12px] text-ink-soft">
              <tr>
                <th scope="col" className={TH}>نماد</th>
                <th scope="col" className={TH}>قیمت (ریال)</th>
                <th scope="col" className={TH}>تغییر</th>
                <th scope="col" className={TH}>نزدیک‌ترین سررسید</th>
                <th scope="col" className={TH}>تعداد قرارداد</th>
                <th scope="col" className={TH}>ارزش معاملات اختیار (میلیارد تومان)</th>
              </tr>
            </thead>
            <tbody>
              {data.map((u) => {
                const next = u.expiries[0];
                const base = `/option-chain?underlying=${encodeURIComponent(u.ins_code)}`;
                return (
                  <tr key={u.ins_code} className="group transition-colors duration-100 hover:bg-paper">
                    <th scope="row" className="whitespace-nowrap border-b border-rule/70 px-4 py-2 text-start font-semibold text-ink group-last:border-b-0">
                      <Link
                        href={base}
                        className="-mx-2 inline-flex min-h-10 items-center rounded-md px-2 underline-offset-4 transition-colors duration-150 hover:bg-ledger hover:underline"
                      >
                        {u.symbol}
                      </Link>
                    </th>
                    <td className={TD}>{fmtInt(u.price)}</td>
                    <td className={TD}>
                      <Change value={u.change_pct} />
                    </td>
                    <td className={TD}>
                      {next ? (
                        <Link
                          href={`${base}&expiry=${next.date}`}
                          className="group/link -mx-2 inline-flex min-h-10 items-center gap-2 rounded-md px-2 transition-colors duration-150 hover:bg-ledger"
                        >
                          <span className="underline-offset-4 group-hover/link:underline">{fmtJalali(next.date)}</span>
                          <span className="text-[12px] text-ink-soft">({fmtDays(next.days)})</span>
                        </Link>
                      ) : (
                        DASH
                      )}
                    </td>
                    <td className={TD}>{fmtInt(u.contracts)}</td>
                    <td className={TD}>{fmtDecimal(u.total_value / 1e10, 1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}