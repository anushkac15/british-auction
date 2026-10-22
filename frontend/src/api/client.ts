import { updateServerClock } from "../hooks/serverClock";
import type {
  AuthResponse,
  BidInput,
  BidResponse,
  ListResponse,
  LoginInput,
  MeResponse,
  RegisterInput,
  RfqCreateInput,
  RfqDetailResponse,
  RfqSummary,
} from "./types";

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setApiToken(token: string | null) {
  authToken = token;
}

/** Called when a request made with a token comes back 401 (expired or revoked session). */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public field: string | null = null,
    public errors: { field: string | null; message: string }[] = [],
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const sentToken = authToken;
  if (sentToken) headers.set("Authorization", `Bearer ${sentToken}`);

  const started = Date.now();
  const res = await fetch(`/api${path}`, { ...init, headers });
  const body = await res.json().catch(() => ({}));
  if (body && typeof body.server_now === "string") updateServerClock(body.server_now, started, Date.now());

  if (!res.ok) {
    if (res.status === 401 && sentToken && sentToken === authToken) onUnauthorized?.();
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`;
    throw new ApiError(res.status, detail, body.field ?? null, body.errors ?? []);
  }
  return body as T;
}

export const api = {
  register: (input: RegisterInput) =>
    request<AuthResponse>("/auth/register", { method: "POST", body: JSON.stringify(input) }),
  login: (input: LoginInput) => request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify(input) }),
  me: () => request<MeResponse>("/auth/me"),
  listRfqs: () => request<ListResponse<RfqSummary>>("/rfqs"),
  getRfq: (id: number) => request<RfqDetailResponse>(`/rfqs/${id}`),
  createRfq: (input: RfqCreateInput) =>
    request<RfqDetailResponse>("/rfqs", { method: "POST", body: JSON.stringify(input) }),
  placeBid: (rfqId: number, input: BidInput) =>
    request<BidResponse>(`/rfqs/${rfqId}/bids`, { method: "POST", body: JSON.stringify(input) }),
  streamUrl: (rfqId: number) => `/api/rfqs/${rfqId}/stream`,
};
