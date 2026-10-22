"""Concurrent bids must be serialized by SELECT ... FOR UPDATE on the RFQ row."""

import threading
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.clock import FrozenClock
from app.db import SessionLocal
from app.enums import EventType, Role
from app.models import ActivityLog, Bid, Rfq, User
from app.schemas.inputs import BidCreate
from app.services.auction_engine import place_bid
from tests.conftest import T0, make_rfq

N = 8
CLOSE = T0 + timedelta(minutes=30)


def _suppliers(db, n: int) -> list[User]:
    people = [User(name=f"Concurrent {i}", email=f"cc{i}@test", role=Role.SUPPLIER) for i in range(n)]
    db.add_all(people)
    db.commit()
    return people


def _fire(rfq: Rfq, suppliers: list[User], clock: FrozenClock) -> list[BaseException]:
    barrier = threading.Barrier(len(suppliers))
    errors: list[BaseException] = []

    def run(i: int, supplier: User) -> None:
        data = BidCreate(
            carrier_name="C",
            freight_charges=Decimal(1000 - i),
            origin_charges=Decimal("0"),
            destination_charges=Decimal("0"),
            transit_time_days=2,
            quote_validity_date=rfq.pickup_date,
        )
        with SessionLocal() as session:
            barrier.wait()
            try:
                place_bid(session, rfq.id, session.get(User, supplier.id), data, clock)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=run, args=(i, s)) for i, s in enumerate(suppliers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return errors


def test_concurrent_bids_extend_once_each_without_lost_updates(db, users):
    rfq = make_rfq(db, users["buyer"], close=CLOSE, forced=CLOSE + timedelta(hours=1), window=30, extension=1)
    suppliers = _suppliers(db, N)
    clock = FrozenClock(CLOSE - timedelta(minutes=1))

    assert _fire(rfq, suppliers, clock) == []

    db.expire_all()
    final = db.get(Rfq, rfq.id)
    extensions = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.rfq_id == rfq.id, ActivityLog.event_type == EventType.TIME_EXTENDED)
        .order_by(ActivityLog.id)
    ).all()
    assert db.scalar(select(func.count()).select_from(Bid)) == N
    assert len(extensions) == N
    # Each extension starts where the previous one ended: no lost or duplicated updates.
    for prev, nxt in zip(extensions, extensions[1:]):
        assert nxt.old_close_at == prev.new_close_at
    assert final.bid_close_at == CLOSE + timedelta(minutes=N)


def test_concurrent_bids_never_exceed_forced_close(db, users):
    forced = CLOSE + timedelta(minutes=3)
    rfq = make_rfq(db, users["buyer"], close=CLOSE, forced=forced, window=10, extension=1)
    suppliers = _suppliers(db, N)
    clock = FrozenClock(CLOSE - timedelta(minutes=1))

    assert _fire(rfq, suppliers, clock) == []

    db.expire_all()
    final = db.get(Rfq, rfq.id)
    count = lambda et: db.scalar(  # noqa: E731
        select(func.count()).select_from(ActivityLog).where(ActivityLog.rfq_id == rfq.id, ActivityLog.event_type == et)
    )
    assert final.bid_close_at == forced
    assert count(EventType.TIME_EXTENDED) == 3
    assert count(EventType.EXTENSION_CAPPED) == 1
    assert count(EventType.BID_SUBMITTED) == N
