import type { Metadata } from "next";
import PayoffBuilder from "@/components/PayoffBuilder";

export const metadata: Metadata = { title: "ماشین‌حساب سود و زیان استراتژی" };

export default function PayoffCalcPage() {
  return <PayoffBuilder />;
}
