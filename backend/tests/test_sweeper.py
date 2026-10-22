from datetime import timedelta

from sqlalchemy import select

from app.clock import FrozenClock
from app.enums import AuctionStatus, EventType
from app.models import ActivityLog, Rfq
from app.services.status import resolve_status, sweep
from tests.conftest import T0, make_rfq

CLOSE = T0 + timedelta(minutes=30)
FORCED = T0 + timedelta(minutes=60)


def log_types(db, rfq):
    return [
        e.event_type
        for e in db.scalars(
            select(ActivityLog).where(ActivityLog.rfq_id == rfq.id).order_by(ActivityLog.created_at, ActivityLog.id)
        )
    ]


def test_resolve_status(db, users):
    rfq = make_rfq(db, users["buyer"])
    assert resolve_status(rfq, T0 - timedelta(seconds=1)) == AuctionStatus.UPCOMING
    assert resolve_status(rfq, T0) == AuctionStatus.ACTIVE
    assert resolve_status(rfq, CLOSE) == AuctionStatus.CLOSED
    rfq.bid_close_at = FORCED
    assert resolve_status(rfq, FORCED) == AuctionStatus.FORCE_CLOSED


def test_sweeper_transitions_and_is_idempotent(db, users):
    rfq = make_rfq(db, users["buyer"])
    clock = FrozenClock(T0 - timedelta(minutes=1))
    assert sweep(db, clock) == 0

    clock.set(T0 + timedelta(minutes=1))
    assert sweep(db, clock) == 1
    assert sweep(db, clock) == 0
    db.expire_all()
    assert db.get(Rfq, rfq.id).status == AuctionStatus.ACTIVE

    clock.set(CLOSE + timedelta(minutes=5))
    assert sweep(db, clock) == 1
    assert sweep(db, clock) == 0
    db.expire_all()
    assert db.get(Rfq, rfq.id).status == AuctionStatus.CLOSED
    assert log_types(db, rfq) == [EventType.RFQ_CREATED, EventType.AUCTION_STARTED, EventType.CLOSED]

    # Entries carry the time the transition happened, not when the sweeper noticed it.
    closed = db.scalar(select(ActivityLog).where(ActivityLog.event_type == EventType.CLOSED))
    assert closed.created_at == CLOSE


def test_lagging_sweeper_skips_straight_to_closed(db, users):
    rfq = make_rfq(db, users["buyer"])
    assert sweep(db, FrozenClock(CLOSE + timedelta(hours=1))) == 1
    db.expire_all()
    assert db.get(Rfq, rfq.id).status == AuctionStatus.CLOSED
    assert log_types(db, rfq) == [EventType.RFQ_CREATED, EventType.AUCTION_STARTED, EventType.CLOSED]


def test_force_closed_when_close_reached_forced(db, users):
    rfq = make_rfq(db, users["buyer"])
    rfq.bid_close_at = rfq.forced_close_at
    db.commit()
    sweep(db, FrozenClock(FORCED))
    db.expire_all()
    assert db.get(Rfq, rfq.id).status == AuctionStatus.FORCE_CLOSED
    assert EventType.FORCE_CLOSED in log_types(db, rfq)
