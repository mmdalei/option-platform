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
        <header className="border-b border-rule bg-panel">
          <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-x-8 gap-y-2 px-4 py-3">
            <nav aria-label="ناوبری اصلی" className="flex flex-wrap items-center gap-x-7 gap-y-1">
              <span className="text-[17px] font-bold">تابلوی اختیار</span>
              <NavLink href="/">دارایی‌های پایه</NavLink>
              <NavLink href="/option-chain">زنجیره قراردادها</NavLink>
              <NavLink href="/payoff-calc">ماشین‌حساب استراتژی</NavLink>
            </nav>
            <SourceBadge />
          </div>
        </header>
        <main className="mx-auto max-w-[1500px] px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
