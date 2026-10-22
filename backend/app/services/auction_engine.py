"""British Auction rules: bid acceptance, ranking triggers and time extensions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import Clock
from app.enums import AuctionStatus, EventType, TriggerType
from app.errors import AppError, conflict, invalid, not_found
from app.models import ActivityLog, AuctionConfig, Bid, Rfq, User
from app.schemas.inputs import BidCreate, RfqCreate
from app.services import ranking
from app.services.activity import log_event, notify_change
from app.services.status import resolve_status


@dataclass
class TriggerResult:
    fired: bool
    reason: str = ""


@dataclass
class Extension:
    old_close_at: datetime
    new_close_at: datetime
    reason: str
    capped: bool


@dataclass
class BidOutcome:
    bid: Bid
    rank: int
    participants: int
    extension: Extension | None
    cap_logged: bool


def _position(order: list[int], supplier_id: int) -> int | None:
    return order.index(supplier_id) + 1 if supplier_id in order else None


def evaluate_trigger(
    trigger_type: TriggerType, window_minutes: int, before: list[int], after: list[int], bidder_id: int
) -> TriggerResult:
    """Decide whether a bid inside the trigger window fires an extension.

    `before` / `after` are supplier ids ordered L1 first. Definitions:
    - ANY_RANK_CHANGE: the ordered list differs. A first bid that lands last counts
      (a new entrant changes the order); a price drop that keeps every position does not.
    - L1_CHANGE: the L1 supplier differs. An empty auction has no L1, so the first bid counts;
      L1 lowering its own price does not.
    """
    window = f"within the last {window_minutes} min"
    if trigger_type == TriggerType.ANY_BID:
        return TriggerResult(True, f"Bid received {window} of close")

    if trigger_type == TriggerType.ANY_RANK_CHANGE:
        if before == after:
            return TriggerResult(False)
        old_pos, new_pos = _position(before, bidder_id), _position(after, bidder_id)
        if old_pos is None:
            detail = f"new entrant at L{new_pos}"
        elif old_pos != new_pos:
            detail = f"a supplier moved from L{old_pos} to L{new_pos}"
        else:
            detail = "supplier order changed"
        return TriggerResult(True, f"Supplier ranking changed {window} of close ({detail})")

    old_l1 = before[0] if before else None
    new_l1 = after[0] if after else None
    if old_l1 == new_l1:
        return TriggerResult(False)
    detail = "first bid received" if old_l1 is None else "a new supplier took L1"
    return TriggerResult(True, f"Lowest bidder (L1) changed {window} of close ({detail})")


def _lock_rfq(db: Session, rfq_id: int) -> Rfq:
    rfq = db.scalars(select(Rfq).where(Rfq.id == rfq_id).with_for_update()).one_or_none()
    if rfq is None:
        raise not_found("RFQ")
    return rfq


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def place_bid(db: Session, rfq_id: int, supplier: User, data: BidCreate, clock: Clock) -> BidOutcome:
    """Accept a bid and apply extension rules. Runs in one transaction under a row lock."""
    try:
        rfq = _lock_rfq(db, rfq_id)
        # Read the clock only after the lock, so the time check reflects the latest close time.
        now = clock.now()

        if not (rfq.bid_start_at <= now < rfq.bid_close_at):
            status = resolve_status(rfq, now)
            if status == AuctionStatus.UPCOMING:
                raise conflict("Auction has not started yet", "auction_not_open")
            raise conflict("Auction is closed", "auction_not_open")

        if data.quote_validity_date < rfq.pickup_date:
            raise invalid(
                f"Quote must be valid until at least the pickup date ({rfq.pickup_date.isoformat()})",
                "quote_validity_date",
            )

        before_bids = ranking.ranked_latest_bids(db, rfq.id)
        previous = next((b for b in before_bids if b.supplier_id == supplier.id), None)
        if previous is not None and data.total >= previous.total_price:
            raise invalid(
                f"New total ({_money(data.total)}) must be lower than your previous bid "
                f"({_money(previous.total_price)})",
                "total",
            )

        bid = Bid(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            carrier_name=data.carrier_name,
            freight_charges=data.freight_charges,
            origin_charges=data.origin_charges,
            destination_charges=data.destination_charges,
            transit_time_days=data.transit_time_days,
            quote_validity_date=data.quote_validity_date,
            created_at=now,
        )
        db.add(bid)
        db.flush()

        after_bids = ranking.ranked_latest_bids(db, rfq.id)
        before = [b.supplier_id for b in before_bids]
        after = [b.supplier_id for b in after_bids]
        rank = after.index(supplier.id) + 1

        log_event(
            db, rfq_id=rfq.id, event_type=EventType.BID_SUBMITTED, at=now,
            reason=f"Rank L{rank} of {len(after)} after this bid",
            supplier_id=supplier.id, bid_id=bid.id,
        )

        cfg: AuctionConfig = rfq.config
        extension: Extension | None = None
        cap_logged = False
        in_window = now >= rfq.bid_close_at - timedelta(minutes=cfg.trigger_window_minutes)
        if in_window:
            trigger = evaluate_trigger(cfg.trigger_type, cfg.trigger_window_minutes, before, after, supplier.id)
            if trigger.fired:
                extension, cap_logged = _apply_extension(db, rfq, cfg, trigger, supplier.id, bid.id, now)

        notify_change(db, rfq.id)
        db.commit()
        return BidOutcome(bid=bid, rank=rank, participants=len(after), extension=extension, cap_logged=cap_logged)
    except Exception:
        db.rollback()
        raise


def _apply_extension(
    db: Session, rfq: Rfq, cfg: AuctionConfig, trigger: TriggerResult, supplier_id: int, bid_id: int, now: datetime
) -> tuple[Extension | None, bool]:
    old_close = rfq.bid_close_at
    if old_close >= rfq.forced_close_at:
        # Already at the forced close. Record that once per RFQ; later triggers write nothing.
        already = db.scalar(
            select(
                exists().where(
                    ActivityLog.rfq_id == rfq.id, ActivityLog.event_type == EventType.EXTENSION_CAPPED
                )
            )
        )
        logged = False
        if not already:
            logged = log_event(
                db, rfq_id=rfq.id, event_type=EventType.EXTENSION_CAPPED, at=now,
                reason=f"{trigger.reason}, but the forced close time has been reached",
                supplier_id=supplier_id, bid_id=bid_id, old_close_at=old_close, new_close_at=old_close,
            )
        return None, logged

    wanted = old_close + timedelta(minutes=cfg.extension_minutes)
    new_close = min(wanted, rfq.forced_close_at)
    capped = new_close < wanted
    if capped:
        added = (new_close - old_close).total_seconds() / 60
        reason = f"{trigger.reason}; extended to the forced close (+{added:g} min, cap reached)"
    else:
        reason = f"{trigger.reason}; extended by {cfg.extension_minutes} min"

    rfq.bid_close_at = new_close
    log_event(
        db, rfq_id=rfq.id, event_type=EventType.TIME_EXTENDED, at=now, reason=reason,
        supplier_id=supplier_id, bid_id=bid_id, old_close_at=old_close, new_close_at=new_close,
    )
    return Extension(old_close, new_close, reason, capped), False


def create_rfq(db: Session, buyer: User, data: RfqCreate, clock: Clock, grace_seconds: int = 0) -> Rfq:
    now = clock.now()
    if data.bid_start_at <= now - timedelta(seconds=grace_seconds):
        raise invalid("Bid start time must be in the future", "bid_start_at")
    if db.scalar(select(exists().where(Rfq.reference_id == data.reference_id))):
        raise conflict(f"Reference ID '{data.reference_id}' already exists", "duplicate_reference")

    rfq = Rfq(
        reference_id=data.reference_id,
        name=data.name,
        buyer_id=buyer.id,
        pickup_date=data.pickup_date,
        bid_start_at=data.bid_start_at,
        original_bid_close_at=data.bid_close_at,
        bid_close_at=data.bid_close_at,
        forced_close_at=data.forced_close_at,
        status=resolve_status_for_new(data.bid_start_at, now),
        config=AuctionConfig(
            trigger_window_minutes=data.trigger_window_minutes,
            extension_minutes=data.extension_minutes,
            trigger_type=data.trigger_type,
        ),
    )
    db.add(rfq)
    try:
        db.flush()
        log_event(
            db, rfq_id=rfq.id, event_type=EventType.RFQ_CREATED, at=now,
            reason="RFQ created with British Auction enabled",
        )
        if rfq.status == AuctionStatus.ACTIVE:
            log_event(
                db, rfq_id=rfq.id, event_type=EventType.AUCTION_STARTED, at=rfq.bid_start_at,
                reason="Auction opened for bidding",
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_rfqs_reference_id" in str(exc.orig):
            raise conflict(f"Reference ID '{data.reference_id}' already exists", "duplicate_reference") from exc
        raise AppError(422, "RFQ violates a database constraint", "constraint_violation") from exc
    return rfq


def resolve_status_for_new(start: datetime, now: datetime) -> AuctionStatus:
    return AuctionStatus.UPCOMING if now < start else AuctionStatus.ACTIVE
