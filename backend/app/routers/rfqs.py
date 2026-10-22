from fastapi import APIRouter, status
from sqlalchemy import select

from app.config import settings
from app.deps import Buyer, ClockDep, CurrentUser, DbSession, Supplier
from app.errors import not_found
from app.models import Rfq, User
from app.schemas.inputs import BidCreate, RfqCreate
from app.schemas.outputs import (
    BidResponse,
    ExtensionOut,
    RfqDetailResponse,
    RfqListResponse,
    UserOut,
)
from app.services import auction_engine, views
from app.services.status import resolve_status, sync_status

router = APIRouter(tags=["rfqs"])


def _detail_response(db, rfq: Rfq, viewer: User, now) -> RfqDetailResponse:
    return RfqDetailResponse(
        server_now=now,
        viewer=UserOut(id=viewer.id, name=viewer.name, role=viewer.role),
        rfq=views.detail_view(db, rfq, viewer, now),
    )


@router.get("/rfqs", response_model=RfqListResponse)
def list_rfqs(db: DbSession, clock: ClockDep, user: CurrentUser) -> RfqListResponse:
    now = clock.now()
    return RfqListResponse(server_now=now, items=views.list_view(db, user, now))


@router.post("/rfqs", response_model=RfqDetailResponse, status_code=status.HTTP_201_CREATED)
def create_rfq(data: RfqCreate, db: DbSession, clock: ClockDep, buyer: Buyer) -> RfqDetailResponse:
    rfq = auction_engine.create_rfq(db, buyer, data, clock, settings.start_time_grace_seconds)
    return _detail_response(db, rfq, buyer, clock.now())


@router.get("/rfqs/{rfq_id}", response_model=RfqDetailResponse)
def get_rfq(rfq_id: int, db: DbSession, clock: ClockDep, user: CurrentUser) -> RfqDetailResponse:
    rfq = db.get(Rfq, rfq_id)
    if rfq is None or not views.buyer_can_view(rfq, user):
        raise not_found("RFQ")
    now = clock.now()
    if resolve_status(rfq, now) != rfq.status:
        # Self-heal the cached status (and its log entries) without waiting for the sweeper.
        # SKIP LOCKED: if a bid holds the lock, just serve the resolved status this time.
        locked = db.scalars(
            select(Rfq).where(Rfq.id == rfq_id).with_for_update(skip_locked=True)
        ).one_or_none()
        if locked is not None:
            sync_status(db, locked, now)
        db.commit()
    return _detail_response(db, rfq, user, now)


@router.post("/rfqs/{rfq_id}/bids", response_model=BidResponse, status_code=status.HTTP_201_CREATED)
def place_bid(rfq_id: int, data: BidCreate, db: DbSession, clock: ClockDep, supplier: Supplier) -> BidResponse:
    outcome = auction_engine.place_bid(db, rfq_id, supplier, data, clock)
    rfq = db.get(Rfq, rfq_id)
    ext = outcome.extension
    return BidResponse(
        server_now=clock.now(),
        quote=views.quote_out(outcome.bid),
        rank=outcome.rank,
        participant_count=outcome.participants,
        bid_close_at=rfq.bid_close_at,
        forced_close_at=rfq.forced_close_at,
        extension=ExtensionOut(
            old_close_at=ext.old_close_at, new_close_at=ext.new_close_at, reason=ext.reason, capped=ext.capped
        )
        if ext
        else None,
    )
