/**
 * Formatting for a Persian (RTL) interface: Persian digits and separators, Jalali dates.
 * `parseNumber` is the inverse: it accepts numbers typed on a Persian keyboard.
 */

export const DASH = "—";

type Num = number | null | undefined;

const integer = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const decimalFormats = new Map<number, Intl.NumberFormat>();
const percentFormats = new Map<number, Intl.NumberFormat>();

function decimalFormat(digits: number): Intl.NumberFormat {
  let format = decimalFormats.get(digits);
  if (!format) {
    format = new Intl.NumberFormat("fa-IR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    decimalFormats.set(digits, format);
  }
  return format;
}

function percentFormat(digits: number): Intl.NumberFormat {
  let format = percentFormats.get(digits);
  if (!format) {
    format = new Intl.NumberFormat("fa-IR", {
      style: "percent",
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    percentFormats.set(digits, format);
  }
  return format;
}

/** ۲۴٬۰۰۰ */
export const fmtInt = (value: Num): string => (value == null ? DASH : integer.format(value));

/** ۰٫۵۶ */
export const fmtDecimal = (value: Num, digits = 2): string =>
  value == null ? DASH : decimalFormat(digits).format(value);

/** `fraction` is 0.55 for 55 %  ->  ۵۵٫۰٪ */
export const fmtPercent = (fraction: Num, digits = 1): string =>
  fraction == null ? DASH : percentFormat(digits).format(fraction);

const compact = new Intl.NumberFormat("fa-IR", { notation: "compact", maximumFractionDigits: 1 });

/** Short form for chart axes: ۲٫۳ میلیون */
export const fmtCompact = (value: number): string => compact.format(value);

const jalaliDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** "2026-10-30" -> ۱۴۰۵/۰۸/۰۸ */
export function fmtJalali(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return jalaliDate.format(new Date(year, month - 1, day));
}

const clock = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "Asia/Tehran",
});

/** ISO timestamp -> ۱۰:۳۷:۳۵ in Tehran time */
export const fmtClock = (isoTimestamp: string): string => clock.format(new Date(isoTimestamp));

export const fmtDays = (days: number): string => `${integer.format(days)} روز`;

/**
 * Parses what a person types: Persian or Arabic digits, thousands separators
 * (`,` or `٬`) and the Persian decimal point (`٫`). Returns null for empty or invalid input.
 */
export function parseNumber(text: string): number | null {
  const normalised = text
    .replace(/[۰-۹]/g, (ch) => String(ch.charCodeAt(0) - 0x06f0))
    .replace(/[٠-٩]/g, (ch) => String(ch.charCodeAt(0) - 0x0660))
    .replace(/[,٬\s]/g, "")
    .replace(/٫/g, ".");
  if (normalised === "") return null;
  const value = Number(normalised);
  return Number.isFinite(value) ? value : null;
}
