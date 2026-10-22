from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bid


def rank_key(bid: Bid) -> tuple:
    # Lowest total wins; on a tie the earlier bid keeps the better rank.
    return (bid.total_price, bid.created_at, bid.id)


def latest_bids_by_rfq(db: Session, rfq_ids: Iterable[int]) -> dict[int, list[Bid]]:
    """Each supplier's latest bid per RFQ, ranked L1 first."""
    ids = list(rfq_ids)
    if not ids:
        return {}
    stmt = (
        select(Bid)
        .where(Bid.rfq_id.in_(ids))
        .distinct(Bid.rfq_id, Bid.supplier_id)
        .order_by(Bid.rfq_id, Bid.supplier_id, Bid.created_at.desc(), Bid.id.desc())
    )
    grouped: dict[int, list[Bid]] = defaultdict(list)
    for bid in db.scalars(stmt):
        grouped[bid.rfq_id].append(bid)
    return {rfq_id: sorted(bids, key=rank_key) for rfq_id, bids in grouped.items()}


def ranked_latest_bids(db: Session, rfq_id: int) -> list[Bid]:
    return latest_bids_by_rfq(db, [rfq_id]).get(rfq_id, [])
