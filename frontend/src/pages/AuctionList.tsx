import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { useServerNow } from "../hooks/serverClock";
import { formatDateTime, formatDuration, formatMoney, liveStatus } from "../lib/format";

export function AuctionList() {
  const { user } = useCurrentUser();
  const now = useServerNow(1000);
  const query = useQuery({
    queryKey: ["rfqs", user?.id],
    queryFn: api.listRfqs,
    enabled: !!user,
    refetchInterval: 5000,
  });
  const isSupplier = user?.role === "SUPPLIER";

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>British Auctions</h1>
          <p className="muted">All RFQs with British Auction bidding. Times are shown in your local time zone.</p>
        </div>
        {user?.role === "BUYER" && (
          <Link className="button" to="/rfqs/new">
            + Create RFQ
          </Link>
        )}
      </div>

      {query.isLoading && <p className="muted">Loading…</p>}
      {query.error && <div className="error">{query.error.message}</div>}
      {query.data && query.data.items.length === 0 && (
        <div className="card empty">No auctions yet.{user?.role === "BUYER" && " Create the first RFQ."}</div>
      )}

      {query.data && query.data.items.length > 0 && (
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
              {query.data.items.map((rfq) => {
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
                    <td>{rfq.participant_count} supplier{rfq.participant_count === 1 ? "" : "s"}</td>
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
      )}
    </section>
  );
}
