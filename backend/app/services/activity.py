from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.enums import ONCE_PER_RFQ_EVENTS, ONCE_PER_RFQ_WHERE, EventType
from app.models import ActivityLog

RFQ_EVENTS_CHANNEL = "rfq_events"


def log_event(
    db: Session,
    *,
    rfq_id: int,
    event_type: EventType,
    at: datetime,
    reason: str,
    supplier_id: int | None = None,
    bid_id: int | None = None,
    old_close_at: datetime | None = None,
    new_close_at: datetime | None = None,
) -> bool:
    """Insert an activity entry. Returns False if a once-per-RFQ event already exists."""
    values = dict(
        rfq_id=rfq_id,
        event_type=event_type,
        reason=reason,
        supplier_id=supplier_id,
        bid_id=bid_id,
        old_close_at=old_close_at,
        new_close_at=new_close_at,
        created_at=at,
    )
    if event_type in ONCE_PER_RFQ_EVENTS:
        stmt = (
            pg_insert(ActivityLog)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["rfq_id", "event_type"], index_where=text(ONCE_PER_RFQ_WHERE)
            )
        )
        return db.execute(stmt).rowcount == 1
    db.add(ActivityLog(**values))
    # Flush now so ids follow call order (ties on created_at are ordered by id).
    db.flush()
    return True


def notify_change(db: Session, rfq_id: int) -> None:
    """Postgres NOTIFY, delivered to listeners when the transaction commits."""
    db.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": RFQ_EVENTS_CHANNEL, "payload": str(rfq_id)})
