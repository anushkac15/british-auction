"""Seed users, and optionally a live demo auction.

    python -m app.seed            # buyer + 4 suppliers (idempotent), all with password DEMO_PASSWORD
    python -m app.seed --demo     # also an RFQ that closes in ~3 min (X=1, Y=1, forced ~6 min)
"""

import argparse
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import system_clock
from app.db import SessionLocal
from app.enums import AuctionStatus, EventType, Role, TriggerType
from app.models import AuctionConfig, Rfq, User
from app.security import hash_password
from app.services.activity import log_event

DEMO_PASSWORD = "password123"

USERS = [
    ("Acme Buyer", "buyer@acme.test", Role.BUYER),
    ("BlueDart Logistics", "bluedart@suppliers.test", Role.SUPPLIER),
    ("Maersk Freight", "maersk@suppliers.test", Role.SUPPLIER),
    ("DHL Global", "dhl@suppliers.test", Role.SUPPLIER),
    ("Gati Cargo", "gati@suppliers.test", Role.SUPPLIER),
]


def seed_users(db: Session) -> list[User]:
    users = []
    for name, email, role in USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(name=name, email=email, role=role)
            db.add(user)
        if user.password_hash is None:
            user.password_hash = hash_password(DEMO_PASSWORD)
        users.append(user)
    db.commit()
    return users


def seed_demo(db: Session, buyer: User) -> Rfq:
    now = system_clock.now().replace(microsecond=0)
    start = now + timedelta(seconds=10)
    close = now + timedelta(minutes=3)
    forced = now + timedelta(minutes=6)
    rfq = Rfq(
        reference_id=f"DEMO-{now:%Y%m%d-%H%M%S}",
        name="Demo: Mumbai -> Delhi FTL (live)",
        buyer_id=buyer.id,
        pickup_date=(forced + timedelta(days=2)).date(),
        bid_start_at=start,
        original_bid_close_at=close,
        bid_close_at=close,
        forced_close_at=forced,
        status=AuctionStatus.UPCOMING,
        config=AuctionConfig(trigger_window_minutes=1, extension_minutes=1, trigger_type=TriggerType.ANY_RANK_CHANGE),
    )
    db.add(rfq)
    db.flush()
    log_event(db, rfq_id=rfq.id, event_type=EventType.RFQ_CREATED, at=now, reason="Demo RFQ created by seed script")
    db.commit()
    return rfq


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="create a live demo RFQ")
    args = parser.parse_args()

    with SessionLocal() as db:
        users = seed_users(db)
        print("Users:", ", ".join(f"{u.email} ({u.role})" for u in users), f"- password: {DEMO_PASSWORD}")
        if args.demo:
            rfq = seed_demo(db, users[0])
            print(f"Demo RFQ id={rfq.id} ref={rfq.reference_id}")
            print(f"  starts {rfq.bid_start_at:%H:%M:%S} UTC, closes {rfq.bid_close_at:%H:%M:%S} UTC, "
                  f"forced close {rfq.forced_close_at:%H:%M:%S} UTC")
            print(f"Run: python scripts/demo_bidder.py --rfq {rfq.id}")


if __name__ == "__main__":
    main()
