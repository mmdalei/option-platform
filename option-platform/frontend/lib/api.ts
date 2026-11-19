/** Types mirror backend/schemas.py. Prices are Rials; `iv` is a fraction (0.55 = 55 %). */

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
export const WS_URL = API_URL.replace(/^http/, "ws");

export type Moneyness = "ITM" | "ATM" | "OTM";
export type PriceSource = "mid" | "last" | "close";

export interface OptionLeg {
  ins_code: string;
  symbol: string;
  last: number | null;
  close: number | null;
  yesterday: number | null;
  change_pct: number | null;
  bid: number | null;
  ask: number | null;
  bid_volume: number | null;
  ask_volume: number | null;
  volume: number;
  value: number | null;
  trades: number | null;
  open_interest: number | null;
  oi_change: number | null;
  price_used: number | null;
  price_source: PriceSource | null;
  iv: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  moneyness: Moneyness | null;
}

export interface ChainRow {
  strike: number;
  is_atm: boolean;
  call: OptionLeg | null;
  put: OptionLeg | null;
}

export interface UnderlyingQuote {
  ins_code: string;
  symbol: string;
  price: number | null;
  last: number | null;
  close: number | null;
  yesterday: number | null;
  change_pct: number | null;
}

export interface ExpiryInfo {
  date: string; // ISO yyyy-mm-dd
  days: number;
}

export interface UnderlyingMeta extends UnderlyingQuote {
  contracts: number;
  total_value: number;
  expiries: ExpiryInfo[];
}

export interface ChainResponse {
  underlying: UnderlyingQuote;
  expiry: string;
  days_to_expiry: number;
  contract_size: number;
  updated_at: string;
  params: Record<string, number | string>;
  rows: ChainRow[];
}

export interface Health {
  status: "starting" | "ok" | "stale";
  source: "live" | "demo";
  last_update: string | null;
  age_seconds: number | null;
  last_error: string | null;
  cache: "memory" | "redis";
  contracts: number;
  poll_interval: number;
}

export interface PayoffLegInput {
  kind: "call" | "put" | "stock";
  side: "long" | "short";
  quantity: number;
  price: number;
  strike: number | null;
  contract_size: number;
}

export interface PayoffRequest {
  legs: PayoffLegInput[];
  spot?: number | null;
  x_min?: number | null;
  x_max?: number | null;
  points?: number;
}

export interface PayoffResponse {
  x: number[];
  y: number[];
  break_evens: number[];
  max_profit: number | null;
  max_loss: number | null;
  profit_unbounded: boolean;
  loss_unbounded: boolean;
  net_premium: number;
  pnl_at_spot: number | null;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("؛ ");
    } catch {
      /* keep statusText */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const getHealth = () => request<Health>("/api/health");
export const getUnderlyings = () => request<UnderlyingMeta[]>("/api/underlyings");

export const getChain = (underlying: string, expiry?: string) =>
  request<ChainResponse>(
    `/api/option-chain?underlying=${encodeURIComponent(underlying)}` +
      (expiry ? `&expiry=${encodeURIComponent(expiry)}` : ""),
  );

export const postPayoff = (body: PayoffRequest, signal?: AbortSignal) =>
  request<PayoffResponse>("/api/payoff", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

/** Persian, user-facing message for any error thrown by the helpers above. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 503)
      return "هنوز داده‌ای دریافت نشده است. اگر منبع داده «زنده» است، دسترسی سرور به TSETMC را بررسی کنید.";
    if (error.status === 404) return "نماد یا سررسید پیدا نشد.";
    if (error.status === 422) return `ورودی نامعتبر است: ${error.message}`;
    return `خطای سرور (${error.status})`;
  }
  return `ارتباط با سرور برقرار نشد. مطمئن شوید بک‌اند روی ${API_URL} اجرا می‌شود.`;
}
