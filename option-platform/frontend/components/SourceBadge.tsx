"use client";

import { useEffect, useState } from "react";
import { getHealth, type Health } from "@/lib/api";
import { cn } from "@/lib/cn";

type Tone = "good" | "warn" | "bad";

const TONES: Record<Tone, string> = {
  good: "border-up/30 bg-itm text-up",
  warn: "border-atm-strong bg-atm text-ink",
  bad: "border-down/30 bg-otm text-down",
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
    tone = "warn";
    label = "داده نمایشی";
  } else if (health.status === "stale") {
    tone = "bad";
    label = "داده قدیمی است";
  } else if (health.status === "starting") {
    tone = "warn";
    label = "در انتظار اولین داده";
  } else {
    tone = "good";
    label = "داده زنده";
  }

  return (
    <span
      role="status"
      className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] font-medium", TONES[tone])}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}
