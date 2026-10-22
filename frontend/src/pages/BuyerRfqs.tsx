import { Link, useParams } from "react-router-dom";

import { RfqTable } from "../components/RfqTable";
import { useRfqList } from "../hooks/useRfqList";
import { useServerNow } from "../hooks/serverClock";

/** Supplier view of one buyer's RFQs. */
export function BuyerRfqs() {
  const buyerId = Number(useParams().buyerId);
  const now = useServerNow(1000);
  const query = useRfqList();
  const rfqs = query.data?.items.filter((r) => r.buyer_id === buyerId) ?? [];
  const buyerName = rfqs[0]?.buyer_name;

  return (
    <section>
      <Link to="/" className="small">
        ← All buyers
      </Link>
      <div className="page-header">
        <div>
          <h1>{buyerName ?? "Buyer"}</h1>
          <p className="muted">RFQs from this buyer. Times are shown in your local time zone.</p>
        </div>
      </div>

      {query.isLoading && <p className="muted">Loading…</p>}
      {query.error && <div className="error">{query.error.message}</div>}
      {query.data && rfqs.length === 0 && <div className="card empty">This buyer has no RFQs.</div>}
      {rfqs.length > 0 && <RfqTable rfqs={rfqs} isSupplier now={now} />}
    </section>
  );
}
