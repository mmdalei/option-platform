import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@fontsource-variable/vazirmatn"; // self-hosted font: no request to Google Fonts
import "./globals.css";
import NavLink from "@/components/NavLink";
import SourceBadge from "@/components/SourceBadge";

export const metadata: Metadata = {
  title: { default: "تابلوی اختیار معامله", template: "%s | تابلوی اختیار معامله" },
  description: "زنجیره قراردادها، نوسان ضمنی، یونانی‌ها و نمودار سود و زیان اختیار معامله بورس تهران",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fa" dir="rtl">
      <body className="min-h-screen bg-paper font-sans text-ink antialiased">
        <header className="sticky top-0 z-30 border-b border-rule bg-panel/95 backdrop-blur-sm">
          <div className="mx-auto flex min-h-14 max-w-[1500px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-2 sm:px-6">
            <nav aria-label="ناوبری اصلی" className="flex flex-wrap items-center gap-x-2 gap-y-1.5 sm:gap-x-3">
              <span className="whitespace-nowrap pe-4 text-[16px] font-bold tracking-tight text-ink sm:border-e sm:border-rule sm:pe-5">
                تابلوی اختیار
              </span>
              <NavLink href="/">دارایی‌های پایه</NavLink>
              <NavLink href="/option-chain">زنجیره قراردادها</NavLink>
              <NavLink href="/payoff-calc">ماشین‌حساب استراتژی</NavLink>
            </nav>
            <div className="flex min-h-8 shrink-0 items-center">
              <SourceBadge />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-[1500px] px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      </body>
    </html>
  );
}