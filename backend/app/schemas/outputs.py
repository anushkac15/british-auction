from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.enums import AuctionStatus, EventType, Role, TriggerType

# Decimal fields serialize to JSON strings (Pydantic v2 default), never floats.


class UserOut(BaseModel):
    id: int
    name: str
    role: Role


class ConfigOut(BaseModel):
    trigger_window_minutes: int
    extension_minutes: int
    trigger_type: TriggerType


class QuoteOut(BaseModel):
    bid_id: int
    carrier_name: str
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    total_price: Decimal
    transit_time_days: int
    quote_validity_date: date
    submitted_at: datetime


class RankingRow(BaseModel):
    rank: int
    label: str
    is_me: bool
    supplier_id: int | None = None
    supplier_name: str | None = None
    bid_count: int
    quote: QuoteOut


class BidHistoryRow(BaseModel):
    supplier_id: int | None = None
    supplier_name: str | None = None
    is_me: bool
    quote: QuoteOut


class ActivityOut(BaseModel):
    id: int
    event_type: EventType
    at: datetime
    message: str
    old_close_at: datetime | None = None
    new_close_at: datetime | None = None
    is_me: bool = False


class RfqSummary(BaseModel):
    id: int
    reference_id: str
    name: str
    buyer_id: int
    buyer_name: str
    pickup_date: date
    bid_start_at: datetime
    original_bid_close_at: datetime
    bid_close_at: datetime
    forced_close_at: datetime
    status: AuctionStatus
    config: ConfigOut
    lowest_bid: Decimal | None
    participant_count: int
    my_rank: int | None = None
    my_best_bid: Decimal | None = None


class RfqListResponse(BaseModel):
    server_now: datetime
    items: list[RfqSummary]


class RfqDetail(RfqSummary):
    bid_count: int
    extension_count: int
    ranking: list[RankingRow]
    bids: list[BidHistoryRow]
    activity: list[ActivityOut]


class RfqDetailResponse(BaseModel):
    server_now: datetime
    viewer: UserOut
    rfq: RfqDetail


class ExtensionOut(BaseModel):
    old_close_at: datetime
    new_close_at: datetime
    reason: str
    capped: bool


class BidResponse(BaseModel):
    server_now: datetime
    quote: QuoteOut
    rank: int
    participant_count: int
    bid_close_at: datetime
    forced_close_at: datetime
    extension: ExtensionOut | None


class AccountOut(UserOut):
    email: str


class MeResponse(BaseModel):
    server_now: datetime
    user: AccountOut


class AuthResponse(MeResponse):
    access_token: str
    token_type: str = "bearer"
