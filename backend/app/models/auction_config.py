from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import TriggerType

if TYPE_CHECKING:
    from app.models.rfq import Rfq

MAX_WINDOW_MINUTES = 60
MAX_EXTENSION_MINUTES = 60


class AuctionConfig(Base):
    __tablename__ = "auction_configs"
    __table_args__ = (
        CheckConstraint(
            f"trigger_window_minutes BETWEEN 1 AND {MAX_WINDOW_MINUTES}", name="trigger_window_range"
        ),
        CheckConstraint(
            f"extension_minutes BETWEEN 1 AND {MAX_EXTENSION_MINUTES}", name="extension_range"
        ),
    )

    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), primary_key=True)
    trigger_window_minutes: Mapped[int] = mapped_column(Integer)
    extension_minutes: Mapped[int] = mapped_column(Integer)
    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType, native_enum=False, length=20, name="trigger_type", create_constraint=True)
    )

    rfq: Mapped["Rfq"] = relationship(back_populates="config")
