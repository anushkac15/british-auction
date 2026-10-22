import { Link } from "react-router-dom";

import type { RfqSummary } from "../api/types";
import { useRfqList } from "../hooks/useRfqList";
import { useServerNow } from "../hooks/serverClock";
import { liveStatus } from "../lib/format";

interface BuyerGroup {
  id: number;
  name: string;
  total: number;
  live: number;
  upcoming: number;
  bidOn: number;
}

function groupByBuyer(rfqs: RfqSummary[], now: number): BuyerGroup[] {
  const groups = new Map<number, BuyerGroup>();
  for (const rfq of rfqs) {
    const group = groups.get(rfq.buyer_id) ?? {
      id: rfq.buyer_id,
      name: rfq.buyer_name,
      total: 0,
      live: 0,
      upcoming: 0,
      bidOn: 0,
    };
    const status = liveStatus(rfq, now);
    group.total += 1;
    if (status === "ACTIVE") group.live += 1;
    if (status === "UPCOMING") group.upcoming += 1;
    if (rfq.my_rank) group.bidOn += 1;
    groups.set(rfq.buyer_id, group);
  }
  // Buyers with live auctions first, then upcoming, then alphabetically.
  return [...groups.values()].sort(
    (a, b) => b.live - a.live || b.upcoming - a.upcoming || a.name.localeCompare(b.name),
  );
}

/** Supplier home: every buyer that has RFQs, each linking to that buyer's RFQs. */
export function BuyerList() {
  const now = useServerNow(1000);
  const query = useRfqList();
  const buyers = query.data ? groupByBuyer(query.data.items, now) : [];

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>Buyers</h1>
          <p className="muted">Choose a buyer to see their RFQs and place bids.</p>
        </div>
      </div>

      {query.isLoading && <p className="muted">Loading…</p>}
      {query.error && <div className="error">{query.error.message}</div>}
      {query.data && buyers.length === 0 && <div className="card empty">No buyers have posted RFQs yet. Check back soon.</div>}

      <div className="buyer-grid">
        {buyers.map((b) => (
          <Link key={b.id} to={`/buyers/${b.id}`} className="card buyer-card">
            <span className="buyer-name">{b.name}</span>
            <span className="muted small">
              {b.total} RFQ{b.total === 1 ? "" : "s"}
              {b.bidOn > 0 && ` · you bid on ${b.bidOn}`}
            </span>
            <span className="buyer-badges">
              {b.live > 0 && <span className="badge badge-active">{b.live} live</span>}
              {b.upcoming > 0 && <span className="badge badge-upcoming">{b.upcoming} upcoming</span>}
              {b.live === 0 && b.upcoming === 0 && <span className="badge badge-closed">No open auctions</span>}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
