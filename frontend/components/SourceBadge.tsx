"use client";

import { useEffect, useState } from "react";
import { getHealth, type Health } from "@/lib/api";
import { cn } from "@/lib/cn";

type Tone = "good" | "demo" | "starting" | "bad";

const TONES: Record<Tone, string> = {
  good: "border-up/35 bg-itm text-up",
  demo: "border-dashed border-warn/70 bg-atm text-ink",
  starting: "border-rule-strong bg-ledger text-ink-soft",
  bad: "border-down/40 bg-otm text-down",
};

const MARKERS: Record<Tone, string> = {
  good: "rounded-full bg-up",
  demo: "rounded-[2px] bg-warn",
  starting: "rounded-full border-2 border-ink-soft bg-transparent",
  bad: "rounded-full bg-down",
};

/** Says where the numbers come from, so demo or stale data is never mistaken for live data. */
export default function SourceBadge() {
  const [health, setHealth] = useState<Health | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const next = await getHealth();
        if (!alive) return;
        setHealth(next);
        setUnreachable(false);
      } catch {
        if (alive) setUnreachable(true);
      }
    };
    void tick();
    const timer = setInterval(tick, 15_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  let tone: Tone;
  let label: string;
  if (unreachable) {
    tone = "bad";
    label = "سرور در دسترس نیست";
  } else if (!health) {
    return null;
  } else if (health.source === "demo") {
    tone = "demo";
    label = "داده نمایشی";
  } else if (health.status === "stale") {
    tone = "bad";
    label = "داده قدیمی است";
  } else if (health.status === "starting") {
    tone = "starting";
    label = "در انتظار اولین داده";
  } else {
    tone = "good";
    label = "داده زنده";
  }

  return (
    <span
      role="status"
      className={cn(
        "inline-flex min-h-8 items-center gap-2 whitespace-nowrap rounded-full border px-3 py-1 text-[12px] font-medium",
        TONES[tone],
      )}
    >
      <span aria-hidden className={cn("h-2 w-2 shrink-0", MARKERS[tone])} />
      {label}
    </span>
  );
}