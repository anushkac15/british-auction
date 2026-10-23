"""Tests run against a real PostgreSQL database (FOR UPDATE, DISTINCT ON, partial indexes).

Set TEST_DATABASE_URL to point elsewhere; by default the `auction_test` database on the
docker-compose Postgres is used. The database is created if missing and migrated with Alembic.
"""

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://auction:auction@localhost:5432/auction_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SSE_ENABLED"] = "false"
os.environ["LOGIN_THROTTLE_STORE"] = "memory"

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.clock import FrozenClock, get_clock  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.enums import AuctionStatus, EventType, Role, TriggerType  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuctionConfig, Rfq, User  # noqa: E402
from app.routers.auth import login_throttle  # noqa: E402
from app.security import create_token  # noqa: E402
from app.services.activity import log_event  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
T0 = datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)


def _ensure_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{url.database}"')


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    _ensure_database()
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE activity_logs, bids, auction_configs, rfqs, users RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(T0)


@pytest.fixture
def client(clock):
    login_throttle.clear()
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def users(db) -> dict[str, User]:
    people = {
        "buyer": User(name="Buyer Co", email="buyer@test", role=Role.BUYER),
        "a": User(name="Supplier Alpha", email="a@test", role=Role.SUPPLIER),
        "b": User(name="Supplier Bravo", email="b@test", role=Role.SUPPLIER),
        "c": User(name="Supplier Charlie", email="c@test", role=Role.SUPPLIER),
    }
    db.add_all(people.values())
    db.commit()
    return people


def make_rfq(
    db,
    buyer: User,
    *,
    start: datetime = T0,
    close: datetime = T0 + timedelta(minutes=30),
    forced: datetime = T0 + timedelta(minutes=60),
    window: int = 10,
    extension: int = 5,
    trigger: TriggerType = TriggerType.ANY_BID,
    pickup: date | None = None,
    ref: str = "RFQ-1",
) -> Rfq:
    rfq = Rfq(
        reference_id=ref,
        name=f"Test {ref}",
        buyer_id=buyer.id,
        pickup_date=pickup or (forced + timedelta(days=1)).date(),
        bid_start_at=start,
        original_bid_close_at=close,
        bid_close_at=close,
        forced_close_at=forced,
        status=AuctionStatus.UPCOMING,
        config=AuctionConfig(trigger_window_minutes=window, extension_minutes=extension, trigger_type=trigger),
    )
    db.add(rfq)
    db.flush()
    log_event(db, rfq_id=rfq.id, event_type=EventType.RFQ_CREATED, at=start, reason="created")
    db.commit()
    return rfq


def bid_payload(total: str | Decimal, rfq: Rfq | None = None, **overrides) -> dict:
    payload = {
        "carrier_name": "Carrier",
        "freight_charges": str(total),
        "origin_charges": "0.00",
        "destination_charges": "0.00",
        "transit_time_days": 3,
        "quote_validity_date": ((rfq.pickup_date if rfq else date(2030, 2, 1)) + timedelta(days=7)).isoformat(),
    }
    payload.update(overrides)
    return payload


def as_user(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id)}"}


def place(client, rfq: Rfq, user: User, total, **overrides):
    return client.post(f"/api/rfqs/{rfq.id}/bids", json=bid_payload(total, rfq, **overrides), headers=as_user(user))
