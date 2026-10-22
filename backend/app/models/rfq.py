from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import AuctionStatus

if TYPE_CHECKING:
    from app.models.auction_config import AuctionConfig
    from app.models.user import User


class Rfq(Base):
    __tablename__ = "rfqs"
    __table_args__ = (
        CheckConstraint("original_bid_close_at > bid_start_at", name="original_close_after_start"),
        CheckConstraint("forced_close_at > original_bid_close_at", name="forced_after_original_close"),
        CheckConstraint("bid_close_at > bid_start_at", name="close_after_start"),
        # Equality is allowed: a capped extension sets bid_close_at == forced_close_at.
        CheckConstraint("bid_close_at <= forced_close_at", name="close_not_after_forced"),
        CheckConstraint("bid_close_at >= original_bid_close_at", name="close_never_moves_back"),
        Index("ix_rfqs_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pickup_date: Mapped[date] = mapped_column(Date)
    bid_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    original_bid_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bid_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forced_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Cached value; the source of truth is resolve_status(rfq, now).
    status: Mapped[AuctionStatus] = mapped_column(
        Enum(AuctionStatus, native_enum=False, length=20, name="auction_status", create_constraint=True),
        default=AuctionStatus.UPCOMING,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    buyer: Mapped["User"] = relationship(lazy="selectin")
    config: Mapped["AuctionConfig"] = relationship(
        back_populates="rfq", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
