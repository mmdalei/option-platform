import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone = "error" | "warn" | "info";

const TONES: Record<Tone, string> = {
  error: "border-down/30 border-s-down bg-otm text-down",
  warn: "border-atm-strong border-s-warn bg-atm text-ink",
  info: "border-rule border-s-rule-strong bg-ledger/60 text-ink-soft",
};

/** Inline message: errors announce themselves to screen readers, the rest are polite. */
export default function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("rounded-md border border-s-4 px-4 py-3 text-[14px] leading-6", TONES[tone])}
    >
      {children}
    </div>
  );
}