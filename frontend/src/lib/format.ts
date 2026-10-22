import type { AuctionStatus, Money, RfqSummary, TriggerType } from "../api/types";

const moneyFormat = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Formats a decimal string without converting it to a float (Intl accepts numeric strings). */
export function formatMoney(value: Money | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return moneyFormat.format(value as unknown as number);
}

const MONEY_RE = /^\d{1,10}(\.\d{1,2})?$/;

export function isMoney(value: string): boolean {
  return MONEY_RE.test(value.trim());
}

/** Decimal string -> integer paise, using BigInt so no float rounding can occur. */
export function toCents(value: Money): bigint {
  const [whole, frac = ""] = value.trim().split(".");
  return BigInt(whole || "0") * 100n + BigInt((frac + "00").slice(0, 2));
}

export function fromCents(cents: bigint): Money {
  const sign = cents < 0n ? "-" : "";
  const abs = cents < 0n ? -cents : cents;
  return `${sign}${abs / 100n}.${(abs % 100n).toString().padStart(2, "0")}`;
}

export function sumMoney(values: Money[]): Money | null {
  if (!values.every(isMoney)) return null;
  return fromCents(values.reduce((acc, v) => acc + toCents(v), 0n));
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDuration(ms: number): string {
  if (ms <= 0) return "00:00";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h ${pad(m)}m`;
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

export const STATUS_LABEL: Record<AuctionStatus, string> = {
  UPCOMING: "Upcoming",
  ACTIVE: "Active",
  CLOSED: "Closed",
  FORCE_CLOSED: "Force Closed",
};

export const TRIGGER_LABEL: Record<TriggerType, string> = {
  ANY_BID: "Bid received in last X minutes",
  ANY_RANK_CHANGE: "Any supplier rank change in last X minutes",
  L1_CHANGE: "Lowest bidder (L1) change in last X minutes",
};

/** Client-side mirror of the server's resolve_status, evaluated on the server-corrected clock. */
export function liveStatus(rfq: Pick<RfqSummary, "bid_start_at" | "bid_close_at" | "forced_close_at">, nowMs: number): AuctionStatus {
  const start = Date.parse(rfq.bid_start_at);
  const close = Date.parse(rfq.bid_close_at);
  if (nowMs < start) return "UPCOMING";
  if (nowMs < close) return "ACTIVE";
  return close >= Date.parse(rfq.forced_close_at) ? "FORCE_CLOSED" : "CLOSED";
}
