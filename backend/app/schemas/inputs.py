import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.enums import Role, TriggerType
from app.models.auction_config import MAX_EXTENSION_MINUTES, MAX_WINDOW_MINUTES

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Email = Annotated[NonEmpty, StringConstraints(max_length=200, to_lower=True)]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8

# NUMERIC(12,2) holds values below 10^10.
MAX_TOTAL = Decimal("9999999999.99")


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


class RfqCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: Annotated[NonEmpty, StringConstraints(max_length=50)]
    name: Annotated[NonEmpty, StringConstraints(max_length=200)]
    pickup_date: date
    bid_start_at: AwareDatetime
    bid_close_at: AwareDatetime
    forced_close_at: AwareDatetime
    trigger_window_minutes: int = Field(ge=1, le=MAX_WINDOW_MINUTES)
    extension_minutes: int = Field(ge=1, le=MAX_EXTENSION_MINUTES)
    trigger_type: TriggerType

    @model_validator(mode="after")
    def _check_times(self) -> "RfqCreate":
        self.bid_start_at = _utc(self.bid_start_at)
        self.bid_close_at = _utc(self.bid_close_at)
        self.forced_close_at = _utc(self.forced_close_at)

        if self.bid_close_at <= self.bid_start_at:
            raise ValueError("Bid close time must be after bid start time")
        if self.forced_close_at <= self.bid_close_at:
            raise ValueError("Forced close time must be after bid close time")
        if self.pickup_date < self.forced_close_at.date():
            raise ValueError("Pickup date must be on or after the forced close date (UTC)")
        if timedelta(minutes=self.trigger_window_minutes) > self.bid_close_at - self.bid_start_at:
            raise ValueError("Trigger window cannot be longer than the auction duration")
        return self


class BidCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carrier_name: Annotated[NonEmpty, StringConstraints(max_length=120)]
    freight_charges: Money
    origin_charges: Money
    destination_charges: Money
    transit_time_days: int = Field(gt=0, le=365)
    quote_validity_date: date

    @property
    def total(self) -> Decimal:
        return self.freight_charges + self.origin_charges + self.destination_charges

    @model_validator(mode="after")
    def _check_total(self) -> "BidCreate":
        if self.total > MAX_TOTAL:
            raise ValueError("Total price is too large")
        return self


class RegisterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[NonEmpty, StringConstraints(max_length=120)]
    email: Email
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    role: Role

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        if not EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address")
        return value


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: str = Field(min_length=1, max_length=128)
