"""Role-based response shaping.

Buyer: everything about their own RFQs, nothing about other buyers'. Supplier: own bids and rank, the anonymous L1 price, participant count,
and an activity log where competitors are anonymous and competitor prices never appear.
"""

from collections import Counter
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import EventType, Role
from app.models import ActivityLog, Bid, Rfq, User
from app.schemas.outputs import (
    ActivityOut,
    BidHistoryRow,
    ConfigOut,
    QuoteOut,
    RankingRow,
    RfqDetail,
    RfqSummary,
)
from app.services import ranking
from app.services.status import resolve_status


def quote_out(bid: Bid) -> QuoteOut:
    return QuoteOut(
        bid_id=bid.id,
        carrier_name=bid.carrier_name,
        freight_charges=bid.freight_charges,
        origin_charges=bid.origin_charges,
        destination_charges=bid.destination_charges,
        total_price=bid.total_price,
        transit_time_days=bid.transit_time_days,
        quote_validity_date=bid.quote_validity_date,
        submitted_at=bid.created_at,
    )


def _summary(rfq: Rfq, ranked: list[Bid], viewer: User, now: datetime) -> RfqSummary:
    mine = next((i for i, b in enumerate(ranked) if b.supplier_id == viewer.id), None)
    is_supplier = viewer.role == Role.SUPPLIER
    return RfqSummary(
        id=rfq.id,
        reference_id=rfq.reference_id,
        name=rfq.name,
        buyer_id=rfq.buyer_id,
        buyer_name=rfq.buyer.name,
        pickup_date=rfq.pickup_date,
        bid_start_at=rfq.bid_start_at,
        original_bid_close_at=rfq.original_bid_close_at,
        bid_close_at=rfq.bid_close_at,
        forced_close_at=rfq.forced_close_at,
        status=resolve_status(rfq, now),
        config=ConfigOut(
            trigger_window_minutes=rfq.config.trigger_window_minutes,
            extension_minutes=rfq.config.extension_minutes,
            trigger_type=rfq.config.trigger_type,
        ),
        lowest_bid=ranked[0].total_price if ranked else None,
        participant_count=len(ranked),
        my_rank=(mine + 1) if is_supplier and mine is not None else None,
        my_best_bid=ranked[mine].total_price if is_supplier and mine is not None else None,
    )


def buyer_can_view(rfq: Rfq, viewer: User) -> bool:
    """Buyers only ever see their own RFQs; suppliers can open any RFQ."""
    return viewer.role != Role.BUYER or rfq.buyer_id == viewer.id


def list_view(db: Session, viewer: User, now: datetime) -> list[RfqSummary]:
    query = select(Rfq).order_by(Rfq.bid_start_at.desc(), Rfq.id.desc())
    if viewer.role == Role.BUYER:
        query = query.where(Rfq.buyer_id == viewer.id)
    rfqs = db.scalars(query).all()
    ranked = ranking.latest_bids_by_rfq(db, [r.id for r in rfqs])
    return [_summary(r, ranked.get(r.id, []), viewer, now) for r in rfqs]


def _activity_message(entry: ActivityLog, viewer: User, names: dict[int, str], bids: dict[int, Bid]) -> str:
    is_buyer = viewer.role == Role.BUYER
    is_me = entry.supplier_id is not None and entry.supplier_id == viewer.id
    who = names.get(entry.supplier_id, "Unknown supplier") if is_buyer else ("You" if is_me else "A competitor")

    if entry.event_type == EventType.BID_SUBMITTED:
        bid = bids.get(entry.bid_id)
        if is_buyer or is_me:
            amount = f"{bid.total_price:,.2f}" if bid else "?"
            carrier = f" via {bid.carrier_name}" if bid else ""
            return f"{who} submitted a bid of {amount}{carrier}. {entry.reason}"
        return "A competitor submitted a bid"

    if entry.event_type in (EventType.TIME_EXTENDED, EventType.EXTENSION_CAPPED):
        by = f"{who}'s bid" if is_buyer else ("your bid" if is_me else "a competitor's bid")
        return f"{entry.reason}. Triggered by {by}."

    return entry.reason


def detail_view(db: Session, rfq: Rfq, viewer: User, now: datetime) -> RfqDetail:
    is_buyer = viewer.role == Role.BUYER
    ranked = ranking.ranked_latest_bids(db, rfq.id)
    all_bids = db.scalars(
        select(Bid).where(Bid.rfq_id == rfq.id).order_by(Bid.created_at.desc(), Bid.id.desc())
    ).all()
    bid_counts = Counter(b.supplier_id for b in all_bids)
    names = {b.supplier_id: b.supplier.name for b in all_bids}
    bids_by_id = {b.id: b for b in all_bids}

    ranking_rows = [
        RankingRow(
            rank=i + 1,
            label=f"L{i + 1}",
            is_me=b.supplier_id == viewer.id,
            supplier_id=b.supplier_id if is_buyer else None,
            supplier_name=b.supplier.name if is_buyer else None,
            bid_count=bid_counts[b.supplier_id],
            quote=quote_out(b),
        )
        for i, b in enumerate(ranked)
        if is_buyer or b.supplier_id == viewer.id
    ]
    history = [
        BidHistoryRow(
            supplier_id=b.supplier_id if is_buyer else None,
            supplier_name=b.supplier.name if is_buyer else None,
            is_me=b.supplier_id == viewer.id,
            quote=quote_out(b),
        )
        for b in all_bids
        if is_buyer or b.supplier_id == viewer.id
    ]

    entries = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.rfq_id == rfq.id)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    ).all()
    activity = [
        ActivityOut(
            id=e.id,
            event_type=e.event_type,
            at=e.created_at,
            message=_activity_message(e, viewer, names, bids_by_id),
            old_close_at=e.old_close_at,
            new_close_at=e.new_close_at,
            is_me=e.supplier_id is not None and e.supplier_id == viewer.id,
        )
        for e in entries
    ]

    summary = _summary(rfq, ranked, viewer, now)
    return RfqDetail(
        **summary.model_dump(),
        bid_count=len(all_bids),
        extension_count=sum(1 for e in entries if e.event_type == EventType.TIME_EXTENDED),
        ranking=ranking_rows,
        bids=history,
        activity=activity,
    )
