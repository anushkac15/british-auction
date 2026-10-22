from enum import StrEnum


class Role(StrEnum):
    BUYER = "BUYER"
    SUPPLIER = "SUPPLIER"


class AuctionStatus(StrEnum):
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    FORCE_CLOSED = "FORCE_CLOSED"


class TriggerType(StrEnum):
    ANY_BID = "ANY_BID"
    ANY_RANK_CHANGE = "ANY_RANK_CHANGE"
    L1_CHANGE = "L1_CHANGE"


class EventType(StrEnum):
    RFQ_CREATED = "RFQ_CREATED"
    AUCTION_STARTED = "AUCTION_STARTED"
    BID_SUBMITTED = "BID_SUBMITTED"
    TIME_EXTENDED = "TIME_EXTENDED"
    EXTENSION_CAPPED = "EXTENSION_CAPPED"
    CLOSED = "CLOSED"
    FORCE_CLOSED = "FORCE_CLOSED"


# Events that may appear at most once per RFQ (enforced by a partial unique index).
ONCE_PER_RFQ_EVENTS = (
    EventType.RFQ_CREATED,
    EventType.AUCTION_STARTED,
    EventType.EXTENSION_CAPPED,
    EventType.CLOSED,
    EventType.FORCE_CLOSED,
)
ONCE_PER_RFQ_WHERE = "event_type IN ({})".format(
    ", ".join(f"'{e.value}'" for e in ONCE_PER_RFQ_EVENTS)
)
