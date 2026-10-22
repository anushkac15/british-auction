import { Link } from "react-router-dom";

import { RfqTable } from "../components/RfqTable";
import { useRfqList } from "../hooks/useRfqList";
import { useServerNow } from "../hooks/serverClock";

/** Buyer home: the buyer's own RFQs. */
export function AuctionList() {
  const now = useServerNow(1000);
  const query = useRfqList();

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>British Auctions</h1>
          <p className="muted">Your RFQs with British Auction bidding. Times are shown in your local time zone.</p>
        </div>
        <Link className="button" to="/rfqs/new">
          + Create RFQ
        </Link>
      </div>

      {query.isLoading && <p className="muted">Loading…</p>}
      {query.error && <div className="error">{query.error.message}</div>}
      {query.data && query.data.items.length === 0 && (
        <div className="card empty">You haven't created any RFQs yet. Create your first one.</div>
      )}
      {query.data && query.data.items.length > 0 && <RfqTable rfqs={query.data.items} isSupplier={false} now={now} />}
    </section>
  );
}
