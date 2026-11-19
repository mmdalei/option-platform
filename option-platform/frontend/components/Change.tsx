import { cn } from "@/lib/cn";
import { DASH, fmtDecimal } from "@/lib/format";

interface Props {
  /** Percent change, e.g. 1.25 for +1.25 %. */
  value: number | null | undefined;
  /** Use the lighter greens/reds that stay readable on the dark spot band. */
  onDark?: boolean;
  digits?: number;
}

/** ▲ ۱٫۲۵٪ / ▼ ۰٫۸۰٪ : direction is carried by the arrow and a hidden label, colour is a bonus. */
export default function Change({ value, onDark = false, digits = 2 }: Props) {
  if (value == null) {
    return <span className={onDark ? "text-white/60" : "text-ink-soft"}>{DASH}</span>;
  }
  if (value === 0) {
    return <span className={onDark ? "text-white/80" : "text-ink-soft"}>{fmtDecimal(0, digits)}٪</span>;
  }
  const up = value > 0;
  const tone = up ? (onDark ? "text-[#6EDBA9]" : "text-up") : onDark ? "text-[#FF9A92]" : "text-down";
  return (
    <span className={cn("whitespace-nowrap", tone)}>
      <span aria-hidden className="text-[0.7em]">
        {up ? "▲" : "▼"}
      </span>{" "}
      {fmtDecimal(Math.abs(value), digits)}٪<span className="sr-only">{up ? " افزایش" : " کاهش"}</span>
    </span>
  );
}
