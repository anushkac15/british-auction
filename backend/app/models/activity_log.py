from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import ONCE_PER_RFQ_WHERE, EventType


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_rfq_created", "rfq_id", "created_at"),
        # At most one EXTENSION_CAPPED (and one of each lifecycle event) per RFQ.
        Index(
            "uq_activity_logs_once_per_rfq",
            "rfq_id",
            "event_type",
            unique=True,
            postgresql_where=text(ONCE_PER_RFQ_WHERE),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"))
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, native_enum=False, length=30, name="event_type", create_constraint=True)
    )
    # Never contains supplier names; the actor is linked through supplier_id.
    reason: Mapped[str] = mapped_column(Text)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.id", ondelete="CASCADE"))
    old_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
