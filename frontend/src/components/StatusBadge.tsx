import type { AuctionStatus } from "../api/types";
import { STATUS_LABEL } from "../lib/format";

export function StatusBadge({ status }: { status: AuctionStatus }) {
  return <span className={`badge badge-${status.toLowerCase()}`}>{STATUS_LABEL[status]}</span>;
}
