import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone = "error" | "warn" | "info";

const TONES: Record<Tone, string> = {
  error: "border-down/40 bg-otm text-down",
  warn: "border-atm-strong bg-atm text-ink",
  info: "border-rule bg-panel text-ink-soft",
};

/** Inline message: errors announce themselves to screen readers, the rest are polite. */
export default function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("rounded-md border px-4 py-3 text-[14px]", TONES[tone])}
    >
      {children}
    </div>
  );
}
