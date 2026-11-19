"use client";

import { useId, useMemo, useState, type PointerEvent } from "react";
import { fmtCompact, fmtInt } from "@/lib/format";

interface Props {
  /** Underlying price at expiry (ascending). */
  x: number[];
  /** Strategy profit / loss in Rials for each x. */
  y: number[];
  /** Current underlying price: drawn as a dashed marker. */
  spot?: number | null;
  breakEvens: number[];
}

const W = 960;
const H = 400;
const PAD = { top: 30, right: 24, bottom: 44, left: 104 };

/** "Nice" tick values (1, 2, 2.5, 5 x 10^n) covering [lo, hi]. */
function niceTicks(lo: number, hi: number, target = 5): number[] {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const rough = span / target;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? 10 * magnitude;
  const ticks: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
    ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  }
  return ticks;
}

export default function PayoffChart({ x, y, spot = null, breakEvens }: Props) {
  const uid = useId().replace(/:/g, "");
  const [hover, setHover] = useState<number | null>(null);

  const g = useMemo(() => {
    const xMin = x[0];
    const xMax = x[x.length - 1];
    const yLo = Math.min(0, ...y);
    const yHi = Math.max(0, ...y);
    const pad = (yHi - yLo) * 0.1 || 1;
    const lo = yLo - pad;
    const hi = yHi + pad;
    const plotW = W - PAD.left - PAD.right;
    const plotH = H - PAD.top - PAD.bottom;
    const sx = (v: number) => PAD.left + ((v - xMin) / (xMax - xMin)) * plotW;
    const sy = (v: number) => PAD.top + ((hi - v) / (hi - lo)) * plotH;
    const line = x.map((v, i) => `${i === 0 ? "M" : "L"}${sx(v).toFixed(1)},${sy(y[i]).toFixed(1)}`).join("");
    const zero = sy(0);
    // Closed shape between the curve and the zero line; clipped twice below to colour profit and loss.
    const area = `${line}L${sx(xMax).toFixed(1)},${zero.toFixed(1)}L${sx(xMin).toFixed(1)},${zero.toFixed(1)}Z`;
    return {
      xMin,
      xMax,
      plotW,
      sx,
      sy,
      line,
      area,
      zero,
      xTicks: niceTicks(xMin, xMax, 6),
      yTicks: niceTicks(lo, hi, 5),
    };
  }, [x, y]);

  const onMove = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * W;
    if (px < PAD.left || px > W - PAD.right) {
      setHover(null);
      return;
    }
    const value = g.xMin + ((px - PAD.left) / g.plotW) * (g.xMax - g.xMin);
    let best = 0;
    for (let i = 1; i < x.length; i++) {
      if (Math.abs(x[i] - value) < Math.abs(x[best] - value)) best = i;
    }
    setHover(best);
  };

  const inRange = (v: number) => v >= g.xMin && v <= g.xMax;
  const tooltip =
    hover === null
      ? null
      : (() => {
          const px = g.sx(x[hover]);
          const boxW = 200;
          return {
            px,
            py: g.sy(y[hover]),
            boxX: Math.min(Math.max(px - boxW / 2, PAD.left), W - PAD.right - boxW),
            boxW,
            price: fmtInt(x[hover]),
            pnl: fmtInt(y[hover]),
          };
        })();

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full touch-none select-none"
      style={{ direction: "ltr" }} // keep the price axis increasing to the right, whatever the page direction
      role="img"
      aria-label="نمودار سود و زیان استراتژی در سررسید"
      onPointerMove={onMove}
      onPointerLeave={() => setHover(null)}
    >
      <defs>
        <clipPath id={`${uid}-above`}>
          <rect x={0} y={0} width={W} height={g.zero} />
        </clipPath>
        <clipPath id={`${uid}-below`}>
          <rect x={0} y={g.zero} width={W} height={H - g.zero} />
        </clipPath>
      </defs>

      <text x={PAD.left} y={16} fontSize={12} className="fill-ink-soft">
        سود و زیان در سررسید (ریال)
      </text>

      {g.yTicks.map((tick) => (
        <g key={`y-${tick}`}>
          <line x1={PAD.left} x2={W - PAD.right} y1={g.sy(tick)} y2={g.sy(tick)} className="stroke-rule" strokeWidth={1} />
          <text x={PAD.left - 10} y={g.sy(tick) + 4} textAnchor="end" fontSize={12} className="fill-ink-soft">
            {fmtCompact(tick)}
          </text>
        </g>
      ))}
      {g.xTicks.map((tick) => (
        <text key={`x-${tick}`} x={g.sx(tick)} y={H - PAD.bottom + 20} textAnchor="middle" fontSize={12} className="fill-ink-soft">
          {fmtInt(tick)}
        </text>
      ))}
      <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize={12} className="fill-ink-soft">
        قیمت دارایی پایه در سررسید (ریال)
      </text>

      <path d={g.area} fill="rgba(12,122,77,0.20)" clipPath={`url(#${uid}-above)`} />
      <path d={g.area} fill="rgba(179,38,30,0.18)" clipPath={`url(#${uid}-below)`} />
      <line x1={PAD.left} x2={W - PAD.right} y1={g.zero} y2={g.zero} className="stroke-ink-soft" strokeWidth={1.5} />
      <path d={g.line} fill="none" className="stroke-ink" strokeWidth={2.5} strokeLinejoin="round" />

      {spot != null && inRange(spot) && (
        <g>
          <line x1={g.sx(spot)} x2={g.sx(spot)} y1={PAD.top} y2={H - PAD.bottom} className="stroke-ink-soft" strokeDasharray="5 4" />
          <text x={g.sx(spot)} y={PAD.top - 6} textAnchor="middle" fontSize={11} className="fill-ink-soft">
            قیمت فعلی
          </text>
        </g>
      )}

      {breakEvens.filter(inRange).map((be) => (
        <g key={`be-${be}`}>
          <circle cx={g.sx(be)} cy={g.zero} r={5} className="fill-panel stroke-ink" strokeWidth={2} />
          <text x={g.sx(be)} y={g.zero + 20} textAnchor="middle" fontSize={11} className="fill-ink">
            {fmtInt(be)}
          </text>
        </g>
      ))}

      {tooltip && (
        <g pointerEvents="none">
          <line x1={tooltip.px} x2={tooltip.px} y1={PAD.top} y2={H - PAD.bottom} className="stroke-ink-soft" strokeDasharray="3 3" />
          <circle cx={tooltip.px} cy={tooltip.py} r={4.5} className="fill-ink" />
          <rect x={tooltip.boxX} y={PAD.top + 4} width={tooltip.boxW} height={42} rx={4} className="fill-ink" />
          <text x={tooltip.boxX + tooltip.boxW / 2} y={PAD.top + 21} textAnchor="middle" fontSize={12} className="fill-white">
            {`قیمت: ${tooltip.price}`}
          </text>
          <text x={tooltip.boxX + tooltip.boxW / 2} y={PAD.top + 38} textAnchor="middle" fontSize={12} className="fill-white">
            {`سود/زیان: ${tooltip.pnl}`}
          </text>
        </g>
      )}
    </svg>
  );
}
