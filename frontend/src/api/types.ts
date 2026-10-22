// Money values are decimal strings (e.g. "1234.50"); never converted to floats.
export type Money = string;

export type Role = "BUYER" | "SUPPLIER";
export type AuctionStatus = "UPCOMING" | "ACTIVE" | "CLOSED" | "FORCE_CLOSED";
export type TriggerType = "ANY_BID" | "ANY_RANK_CHANGE" | "L1_CHANGE";
export type EventType =
  | "RFQ_CREATED"
  | "AUCTION_STARTED"
  | "BID_SUBMITTED"
  | "TIME_EXTENDED"
  | "EXTENSION_CAPPED"
  | "CLOSED"
  | "FORCE_CLOSED";

export interface User {
  id: number;
  name: string;
  role: Role;
}

export interface Account extends User {
  email: string;
}

export interface MeResponse {
  server_now: string;
  user: Account;
}

export interface AuthResponse extends MeResponse {
  access_token: string;
  token_type: "bearer";
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterInput extends LoginInput {
  name: string;
  role: Role;
}

export interface AuctionConfig {
  trigger_window_minutes: number;
  extension_minutes: number;
  trigger_type: TriggerType;
}

export interface RfqSummary {
  id: number;
  reference_id: string;
  name: string;
  buyer_id: number;
  buyer_name: string;
  pickup_date: string;
  bid_start_at: string;
  original_bid_close_at: string;
  bid_close_at: string;
  forced_close_at: string;
  status: AuctionStatus;
  config: AuctionConfig;
  lowest_bid: Money | null;
  participant_count: number;
  my_rank: number | null;
  my_best_bid: Money | null;
}

export interface Quote {
  bid_id: number;
  carrier_name: string;
  freight_charges: Money;
  origin_charges: Money;
  destination_charges: Money;
  total_price: Money;
  transit_time_days: number;
  quote_validity_date: string;
  submitted_at: string;
}

export interface RankingRow {
  rank: number;
  label: string;
  is_me: boolean;
  supplier_id: number | null;
  supplier_name: string | null;
  bid_count: number;
  quote: Quote;
}

export interface BidHistoryRow {
  supplier_id: number | null;
  supplier_name: string | null;
  is_me: boolean;
  quote: Quote;
}

export interface Activity {
  id: number;
  event_type: EventType;
  at: string;
  message: string;
  old_close_at: string | null;
  new_close_at: string | null;
  is_me: boolean;
}

export interface RfqDetail extends RfqSummary {
  bid_count: number;
  extension_count: number;
  ranking: RankingRow[];
  bids: BidHistoryRow[];
  activity: Activity[];
}

export interface ListResponse<T> {
  server_now: string;
  items: T[];
}

export interface RfqDetailResponse {
  server_now: string;
  viewer: User;
  rfq: RfqDetail;
}

export interface BidResponse {
  server_now: string;
  quote: Quote;
  rank: number;
  participant_count: number;
  bid_close_at: string;
  forced_close_at: string;
  extension: { old_close_at: string; new_close_at: string; reason: string; capped: boolean } | null;
}

export interface RfqCreateInput {
  reference_id: string;
  name: string;
  pickup_date: string;
  bid_start_at: string;
  bid_close_at: string;
  forced_close_at: string;
  trigger_window_minutes: number;
  extension_minutes: number;
  trigger_type: TriggerType;
}

export interface BidInput {
  carrier_name: string;
  freight_charges: Money;
  origin_charges: Money;
  destination_charges: Money;
  transit_time_days: number;
  quote_validity_date: string;
}
