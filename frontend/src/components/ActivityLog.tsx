import type { Activity, EventType } from "../api/types";
import { formatDateTime, formatTime } from "../lib/format";

const EVENT_LABEL: Record<EventType, string> = {
  RFQ_CREATED: "Created",
  AUCTION_STARTED: "Started",
  BID_SUBMITTED: "Bid",
  TIME_EXTENDED: "Extended",
  EXTENSION_CAPPED: "Cap reached",
  CLOSED: "Closed",
  FORCE_CLOSED: "Force closed",
};

export function ActivityLog({ items }: { items: Activity[] }) {
  if (!items.length) return <p className="muted">No activity yet.</p>;
  return (
    <ol className="timeline">
      {items.map((a) => (
        <li key={a.id} className={`timeline-item event-${a.event_type.toLowerCase()} ${a.is_me ? "mine" : ""}`}>
          <div className="timeline-meta">
            <span className={`tag tag-${a.event_type.toLowerCase()}`}>{EVENT_LABEL[a.event_type]}</span>
            <time className="muted small" dateTime={a.at}>
              {formatDateTime(a.at)}
            </time>
          </div>
          <div>{a.message}</div>
          {a.event_type === "TIME_EXTENDED" && a.old_close_at && a.new_close_at && (
            <div className="small muted">
              Close time {formatTime(a.old_close_at)} → <strong>{formatTime(a.new_close_at)}</strong>
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
