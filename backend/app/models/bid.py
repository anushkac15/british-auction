from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.user import User

MONEY = Numeric(12, 2, asdecimal=True)


class Bid(Base):
    """Append-only. A supplier's latest bid is found with DISTINCT ON, not a flag."""

    __tablename__ = "bids"
    __table_args__ = (
        CheckConstraint("freight_charges >= 0", name="freight_non_negative"),
        CheckConstraint("origin_charges >= 0", name="origin_non_negative"),
        CheckConstraint("destination_charges >= 0", name="destination_non_negative"),
        CheckConstraint("transit_time_days > 0", name="transit_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    carrier_name: Mapped[str] = mapped_column(String(120))
    freight_charges: Mapped[Decimal] = mapped_column(MONEY)
    origin_charges: Mapped[Decimal] = mapped_column(MONEY)
    destination_charges: Mapped[Decimal] = mapped_column(MONEY)
    total_price: Mapped[Decimal] = mapped_column(
        MONEY, Computed("freight_charges + origin_charges + destination_charges", persisted=True)
    )
    transit_time_days: Mapped[int] = mapped_column(Integer)
    quote_validity_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    supplier: Mapped["User"] = relationship(lazy="selectin")


Index("ix_bids_rfq_supplier_created", Bid.rfq_id, Bid.supplier_id, Bid.created_at.desc())
