import { Link } from "react-router-dom";

import type { RfqSummary } from "../api/types";
import { formatDateTime, formatDuration, formatMoney, liveStatus } from "../lib/format";
import { StatusBadge } from "./StatusBadge";

interface Props {
  rfqs: RfqSummary[];
  isSupplier: boolean;
  now: number;
}

export function RfqTable({ rfqs, isSupplier, now }: Props) {
  return (
    <div className="card table-wrap">
      <table>
        <thead>
          <tr>
            <th>RFQ</th>
            <th>Status</th>
            <th className="num">Current lowest bid</th>
            {isSupplier && <th>Your position</th>}
            <th>Bids from</th>
            <th>Current bid close</th>
            <th>Forced close</th>
          </tr>
        </thead>
        <tbody>
          {rfqs.map((rfq) => {
            const status = liveStatus(rfq, now);
            const extended = rfq.bid_close_at !== rfq.original_bid_close_at;
            return (
              <tr key={rfq.id}>
                <td>
                  <Link to={`/rfqs/${rfq.id}`} className="strong">
                    {rfq.name}
                  </Link>
                  <div className="muted small">{rfq.reference_id}</div>
                </td>
                <td>
                  <StatusBadge status={status} />
                  {status === "UPCOMING" && (
                    <div className="muted small">starts in {formatDuration(Date.parse(rfq.bid_start_at) - now)}</div>
                  )}
                  {status === "ACTIVE" && (
                    <div className="muted small">{formatDuration(Date.parse(rfq.bid_close_at) - now)} left</div>
                  )}
                </td>
                <td className="num strong">{formatMoney(rfq.lowest_bid)}</td>
                {isSupplier && (
                  <td>
                    {rfq.my_rank ? (
                      <>
                        <span className={`rank rank-${Math.min(rfq.my_rank, 4)}`}>L{rfq.my_rank}</span>{" "}
                        <span className="small">{formatMoney(rfq.my_best_bid)}</span>
                      </>
                    ) : (
                      <span className="muted small">No bid</span>
                    )}
                  </td>
                )}
                <td>
                  {rfq.participant_count} supplier{rfq.participant_count === 1 ? "" : "s"}
                </td>
                <td>
                  {formatDateTime(rfq.bid_close_at)}
                  {extended && <div className="small extended">extended</div>}
                </td>
                <td>{formatDateTime(rfq.forced_close_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
