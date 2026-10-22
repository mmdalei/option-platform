"use client";

import Link from "next/link";
import Change from "@/components/Change";
import Notice from "@/components/Notice";
import { useUnderlyings } from "@/hooks/useOptionChain";
import { DASH, fmtDays, fmtDecimal, fmtInt, fmtJalali } from "@/lib/format";

const TH = "px-4 py-2.5 text-start font-medium";
const TD = "px-4 py-3 tabular-nums";

export default function DashboardPage() {
  const { data, error } = useUnderlyings();

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">دارایی‌های پایه دارای اختیار معامله</h1>
        <p className="mt-1 text-[14px] text-ink-soft">
          نمادها بر اساس ارزش معاملات اختیار امروز مرتب شده‌اند. برای دیدن زنجیره قراردادها روی نماد بزنید.
        </p>
      </div>

      {!data && error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <div className="h-40 rounded-md border border-rule bg-panel motion-safe:animate-pulse" aria-busy="true" />}
      {data && data.length === 0 && <Notice tone="info">هنوز دارایی پایه‌ای با اختیار معامله ثبت نشده است.</Notice>}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-rule bg-panel">
          <table className="w-full text-[14px]">
            <caption className="sr-only">دارایی‌های پایه دارای اختیار معامله</caption>
            <thead className="text-[12px] text-ink-soft">
              <tr className="border-b border-rule">
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
                  <tr key={u.ins_code} className="border-b border-rule/60 last:border-0 hover:bg-paper">
                    <th scope="row" className="px-4 py-3 text-start font-semibold">
                      <Link href={base} className="underline-offset-4 hover:underline">
                        {u.symbol}
                      </Link>
                    </th>
                    <td className={TD}>{fmtInt(u.price)}</td>
                    <td className={TD}>
                      <Change value={u.change_pct} />
                    </td>
                    <td className={TD}>
                      {next ? (
                        <Link href={`${base}&expiry=${next.date}`} className="underline-offset-4 hover:underline">
                          {fmtJalali(next.date)}
                          <span className="ms-2 text-[12px] text-ink-soft">({fmtDays(next.days)})</span>
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
