from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.clock import Clock
from app.enums import AuctionStatus, EventType
from app.models import Rfq
from app.services.activity import log_event, notify_change

_ORDER = {
    AuctionStatus.UPCOMING: 0,
    AuctionStatus.ACTIVE: 1,
    AuctionStatus.CLOSED: 2,
    AuctionStatus.FORCE_CLOSED: 2,
}


def resolve_status(rfq: Rfq, now: datetime) -> AuctionStatus:
    """Source of truth for status; the stored rfqs.status column is only a cache."""
    if now < rfq.bid_start_at:
        return AuctionStatus.UPCOMING
    if now < rfq.bid_close_at:
        return AuctionStatus.ACTIVE
    if rfq.bid_close_at >= rfq.forced_close_at:
        return AuctionStatus.FORCE_CLOSED
    return AuctionStatus.CLOSED


def is_open(rfq: Rfq, now: datetime) -> bool:
    return rfq.bid_start_at <= now < rfq.bid_close_at


def sync_status(db: Session, rfq: Rfq, now: datetime) -> bool:
    """Persist the resolved status and log transitions. The caller must hold the row lock.

    Log entries are stamped with the moment the transition actually happened, not the
    moment it was noticed, so a lagging sweeper still produces an accurate timeline.
    Idempotent: does nothing when the cached status is already current.
    """
    target = resolve_status(rfq, now)
    if target == rfq.status:
        return False

    if _ORDER[rfq.status] < _ORDER[AuctionStatus.ACTIVE] <= _ORDER[target]:
        log_event(
            db, rfq_id=rfq.id, event_type=EventType.AUCTION_STARTED, at=rfq.bid_start_at,
            reason="Auction opened for bidding",
        )
    if target == AuctionStatus.CLOSED:
        log_event(
            db, rfq_id=rfq.id, event_type=EventType.CLOSED, at=rfq.bid_close_at,
            reason="Auction closed at the bid close time",
        )
    elif target == AuctionStatus.FORCE_CLOSED:
        log_event(
            db, rfq_id=rfq.id, event_type=EventType.FORCE_CLOSED, at=rfq.bid_close_at,
            reason="Auction reached the forced close time; no further extensions possible",
        )

    rfq.status = target
    notify_change(db, rfq.id)
    return True


def sweep(db: Session, clock: Clock) -> int:
    """Persist all due status transitions. Safe to run concurrently (SKIP LOCKED)."""
    now = clock.now()
    due = db.scalars(
        select(Rfq)
        .where(
            or_(
                and_(Rfq.status == AuctionStatus.UPCOMING, Rfq.bid_start_at <= now),
                and_(Rfq.status == AuctionStatus.ACTIVE, Rfq.bid_close_at <= now),
            )
        )
        .order_by(Rfq.id)
        .with_for_update(skip_locked=True)
    ).all()
    changed = sum(1 for rfq in due if sync_status(db, rfq, now))
    db.commit()
    return changed
