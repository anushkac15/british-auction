import type { RfqCreateInput } from "../api/types";

export const MAX_WINDOW_MINUTES = 60;
export const MAX_EXTENSION_MINUTES = 60;

export interface CreateFormValues {
  reference_id: string;
  name: string;
  pickup_date: string; // yyyy-mm-dd
  bid_start_at: string; // datetime-local (browser local time)
  bid_close_at: string;
  forced_close_at: string;
  trigger_window_minutes: string;
  extension_minutes: string;
  trigger_type: RfqCreateInput["trigger_type"];
}

export type FormErrors = Partial<Record<keyof CreateFormValues, string>>;

function localToMs(value: string): number {
  return value ? new Date(value).getTime() : NaN;
}

function utcDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

function intInRange(value: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const n = Number(value);
  return n >= min && n <= max ? n : null;
}

/** Mirrors the API rules so most mistakes are caught before submitting. */
export function validateCreate(v: CreateFormValues, serverNowMs: number): FormErrors {
  const errors: FormErrors = {};
  if (!v.reference_id.trim()) errors.reference_id = "Reference ID is required";
  else if (v.reference_id.trim().length > 50) errors.reference_id = "At most 50 characters";
  if (!v.name.trim()) errors.name = "Name is required";

  const start = localToMs(v.bid_start_at);
  const close = localToMs(v.bid_close_at);
  const forced = localToMs(v.forced_close_at);

  if (Number.isNaN(start)) errors.bid_start_at = "Start time is required";
  else if (start <= serverNowMs) errors.bid_start_at = "Start time must be in the future";

  if (Number.isNaN(close)) errors.bid_close_at = "Close time is required";
  else if (!Number.isNaN(start) && close <= start) errors.bid_close_at = "Close time must be after the start time";

  if (Number.isNaN(forced)) errors.forced_close_at = "Forced close time is required";
  else if (!Number.isNaN(close) && forced <= close)
    errors.forced_close_at = "Forced close time must be after the bid close time";

  if (!v.pickup_date) errors.pickup_date = "Pickup date is required";
  else if (!Number.isNaN(forced) && v.pickup_date < utcDate(forced))
    errors.pickup_date = `Pickup date must be on or after the forced close date (${utcDate(forced)} UTC)`;

  const x = intInRange(v.trigger_window_minutes, 1, MAX_WINDOW_MINUTES);
  if (x === null) errors.trigger_window_minutes = `Whole minutes between 1 and ${MAX_WINDOW_MINUTES}`;
  else if (!Number.isNaN(start) && !Number.isNaN(close) && x * 60_000 > close - start)
    errors.trigger_window_minutes = "Trigger window cannot be longer than the auction duration";

  if (intInRange(v.extension_minutes, 1, MAX_EXTENSION_MINUTES) === null)
    errors.extension_minutes = `Whole minutes between 1 and ${MAX_EXTENSION_MINUTES}`;

  return errors;
}

export function toCreateInput(v: CreateFormValues): RfqCreateInput {
  return {
    reference_id: v.reference_id.trim(),
    name: v.name.trim(),
    pickup_date: v.pickup_date,
    bid_start_at: new Date(v.bid_start_at).toISOString(),
    bid_close_at: new Date(v.bid_close_at).toISOString(),
    forced_close_at: new Date(v.forced_close_at).toISOString(),
    trigger_window_minutes: Number(v.trigger_window_minutes),
    extension_minutes: Number(v.extension_minutes),
    trigger_type: v.trigger_type,
  };
}

/** Formats epoch ms as a value for <input type="datetime-local"> in browser local time. */
export function toLocalInput(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function toLocalDate(ms: number): string {
  return toLocalInput(ms).slice(0, 10);
}
