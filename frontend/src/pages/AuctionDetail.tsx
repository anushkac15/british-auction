import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { RfqDetail } from "../api/types";
import { ActivityLog } from "../components/ActivityLog";
import { BidForm } from "../components/BidForm";
import { Countdown } from "../components/Countdown";
import { StatusBadge } from "../components/StatusBadge";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { useRfqStream } from "../hooks/useRfqStream";
import { useServerNow } from "../hooks/serverClock";
import { TRIGGER_LABEL, formatDate, formatDateTime, formatMoney, formatTime, liveStatus } from "../lib/format";

export function AuctionDetail() {
  const id = Number(useParams().id);
  const { user } = useCurrentUser();
  const now = useServerNow(250);
  const streamRef = useRef(false);

  const query = useQuery({
    queryKey: ["rfq", id, user?.id],
    queryFn: () => api.getRfq(id),
    enabled: !!user && Number.isFinite(id),
    refetchInterval: (q) => {
      const rfq = q.state.data?.rfq;
      if (!rfq) return 3000;
      const status = liveStatus(rfq, Date.now());
      const serverSettled = rfq.status === "CLOSED" || rfq.status === "FORCE_CLOSED";
      if (serverSettled) return false;
      if (status === "CLOSED" || status === "FORCE_CLOSED") return 2000; // pick up the final log entries
      return streamRef.current ? 15000 : 3000;
    },
  });

  const rfq = query.data?.rfq;
  const live = rfq ? liveStatus(rfq, now) : null;
  const streamConnected = useRfqStream(id, !!rfq && (live === "ACTIVE" || live === "UPCOMING"));
  streamRef.current = streamConnected;

  if (query.isLoading) return <p className="muted">Loading…</p>;
  if (query.error) return <div className="error">{query.error.message}</div>;
  if (!rfq || !live) return null;

  const isSupplier = user?.role === "SUPPLIER";

  return (
    <section>
      <Link to={isSupplier ? `/buyers/${rfq.buyer_id}` : "/"} className="small">
        {isSupplier ? `← ${rfq.buyer_name}'s RFQs` : "← All auctions"}
      </Link>
      <div className="page-header">
        <div>
          <h1>
            {rfq.name} <StatusBadge status={live} />
          </h1>
          <p className="muted">
            {rfq.reference_id} · Buyer: {rfq.buyer_name} · Pickup {formatDate(rfq.pickup_date)}
          </p>
        </div>
        <div className="muted small live-indicator">
          {streamConnected ? "● Live (SSE)" : live === "ACTIVE" || live === "UPCOMING" ? "○ Polling every 3s" : ""}
        </div>
      </div>

      {(live === "CLOSED" || live === "FORCE_CLOSED") && <ClosedResult rfq={rfq} isSupplier={isSupplier} />}

      <div className="grid-4">
        {live === "UPCOMING" ? (
          <Countdown label="Bidding opens in" target={rfq.bid_start_at} nowMs={now} />
        ) : (
          <Countdown
            label="Bid close in"
            target={rfq.bid_close_at}
            nowMs={now}
            doneLabel={live === "FORCE_CLOSED" ? "Force closed" : "Closed"}
            highlight={rfq.extension_count > 0}
            note={
              rfq.extension_count > 0
                ? `Extended ${rfq.extension_count}× (originally ${formatTime(rfq.original_bid_close_at)})`
                : undefined
            }
          />
        )}
        <Countdown label="Forced close in" target={rfq.forced_close_at} nowMs={now} doneLabel="Reached" />
        <div className="card stat">
          <div className="muted small">Current lowest bid (L1)</div>
          <div className="stat-value">{formatMoney(rfq.lowest_bid)}</div>
          <div className="small">
            {rfq.participant_count} supplier{rfq.participant_count === 1 ? "" : "s"} · {rfq.bid_count} bid
            {rfq.bid_count === 1 ? "" : "s"}
          </div>
        </div>
        {isSupplier ? (
          <div className="card stat">
            <div className="muted small">Your position</div>
            <div className="stat-value">{rfq.my_rank ? `L${rfq.my_rank}` : "—"}</div>
            <div className="small">
              {rfq.my_rank ? `of ${rfq.participant_count} · your bid ${formatMoney(rfq.my_best_bid)}` : "No bid yet"}
            </div>
          </div>
        ) : (
          <ConfigCard rfq={rfq} />
        )}
      </div>

      {isSupplier && <ConfigCard rfq={rfq} wide />}

      {isSupplier && live === "ACTIVE" && <BidForm key={`${rfq.id}-${user?.id}`} rfq={rfq} />}
      {isSupplier && live === "UPCOMING" && <div className="card muted">Bidding opens at {formatDateTime(rfq.bid_start_at)}.</div>}

      <div className="card">
        <h3>{isSupplier ? "Your quote" : "Supplier ranking"}</h3>
        {isSupplier && (
          <p className="muted small">
            Competitor names and prices are hidden. You can see the current L1 price and your own rank.
          </p>
        )}
        <RankingTable rfq={rfq} showSupplier={!isSupplier} />
      </div>

      <div className="columns">
        <div className="card">
          <h3>Activity log</h3>
          <ActivityLog items={rfq.activity} />
        </div>
        <div className="card">
          <h3>{isSupplier ? "Your bid history" : "All bids"}</h3>
          <BidHistory rfq={rfq} showSupplier={!isSupplier} />
        </div>
      </div>
    </section>
  );
}

function ConfigCard({ rfq, wide }: { rfq: RfqDetail; wide?: boolean }) {
  const { trigger_window_minutes: x, extension_minutes: y, trigger_type } = rfq.config;
  return (
    <div className={`card stat ${wide ? "config-wide" : ""}`}>
      <div className="muted small">Auction configuration</div>
      <div>
        <strong>X = {x} min</strong> trigger window · <strong>Y = {y} min</strong> extension
      </div>
      <div className="small">Trigger: {TRIGGER_LABEL[trigger_type]}</div>
      <div className="muted small">Never extends past the forced close ({formatTime(rfq.forced_close_at)}).</div>
    </div>
  );
}

function ClosedResult({ rfq, isSupplier }: { rfq: RfqDetail; isSupplier: boolean }) {
  if (rfq.participant_count === 0) {
    return (
      <div className="card result-card result-empty">
        <h3>Auction Closed</h3>
        <p className="muted">No bids were received.</p>
      </div>
    );
  }

  if (!isSupplier) {
    const winner = rfq.ranking[0];
    return (
      <div className="card result-card">
        <h3>Auction Closed</h3>
        <dl className="result-list">
          <dt>Winning Supplier</dt>
          <dd>{winner.supplier_name}</dd>
          <dt>Winning Bid</dt>
          <dd>{formatMoney(winner.quote.total_price)}</dd>
          <dt>Rank</dt>
          <dd>{winner.label}</dd>
        </dl>
      </div>
    );
  }

  if (rfq.my_rank === 1) {
    return (
      <div className="card result-card">
        <h3>Auction Closed</h3>
        <p>
          <strong>You won</strong> with a bid of <strong>{formatMoney(rfq.my_best_bid)}</strong> (L1).
        </p>
      </div>
    );
  }

  return (
    <div className="card result-card result-lost">
      <h3>Auction Closed</h3>
      <dl className="result-list">
        <dt>Winning Bid</dt>
        <dd>{formatMoney(rfq.lowest_bid)}</dd>
        <dt>Your final rank</dt>
        <dd>{rfq.my_rank ? `L${rfq.my_rank} of ${rfq.participant_count}` : "You did not bid"}</dd>
      </dl>
    </div>
  );
}

function RankingTable({ rfq, showSupplier }: { rfq: RfqDetail; showSupplier: boolean }) {
  if (!rfq.ranking.length) return <p className="muted">No bids yet.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Rank</th>
            {showSupplier && <th>Supplier</th>}
            <th>Carrier</th>
            <th className="num">Freight</th>
            <th className="num">Origin</th>
            <th className="num">Destination</th>
            <th className="num">Total</th>
            <th>Transit</th>
            <th>Valid until</th>
            <th>Bids</th>
            <th>Last bid</th>
          </tr>
        </thead>
        <tbody>
          {rfq.ranking.map((row) => (
            <tr key={row.quote.bid_id} className={row.is_me ? "mine" : ""}>
              <td>
                <span className={`rank rank-${Math.min(row.rank, 4)}`}>{row.label}</span>
              </td>
              {showSupplier && <td className="strong">{row.supplier_name}</td>}
              <td>{row.quote.carrier_name}</td>
              <td className="num">{formatMoney(row.quote.freight_charges)}</td>
              <td className="num">{formatMoney(row.quote.origin_charges)}</td>
              <td className="num">{formatMoney(row.quote.destination_charges)}</td>
              <td className="num strong">{formatMoney(row.quote.total_price)}</td>
              <td>{row.quote.transit_time_days} d</td>
              <td>{formatDate(row.quote.quote_validity_date)}</td>
              <td>{row.bid_count}</td>
              <td className="small">{formatTime(row.quote.submitted_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BidHistory({ rfq, showSupplier }: { rfq: RfqDetail; showSupplier: boolean }) {
  if (!rfq.bids.length) return <p className="muted">No bids yet.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            {showSupplier && <th>Supplier</th>}
            <th className="num">Total</th>
            <th>Carrier</th>
          </tr>
        </thead>
        <tbody>
          {rfq.bids.map((b) => (
            <tr key={b.quote.bid_id}>
              <td className="small">{formatTime(b.quote.submitted_at)}</td>
              {showSupplier && <td>{b.supplier_name}</td>}
              <td className="num">{formatMoney(b.quote.total_price)}</td>
              <td>{b.quote.carrier_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
