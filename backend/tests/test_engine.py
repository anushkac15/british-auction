from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.enums import EventType, TriggerType
from app.models import ActivityLog, Bid, Rfq
from app.services.auction_engine import evaluate_trigger
from tests.conftest import T0, as_user, make_rfq, place

CLOSE = T0 + timedelta(minutes=30)
FORCED = T0 + timedelta(minutes=60)


def close_at(db, rfq):
    db.expire_all()
    return db.get(Rfq, rfq.id).bid_close_at


def events(db, rfq, event_type):
    return db.scalars(
        select(ActivityLog).where(ActivityLog.rfq_id == rfq.id, ActivityLog.event_type == event_type)
    ).all()


# ---------- pure trigger rules ----------

def test_rank_change_definitions():
    rank = TriggerType.ANY_RANK_CHANGE
    # first bid in an empty auction
    assert evaluate_trigger(rank, 10, [], [1], 1).fired
    # new entrant landing last still changes the order
    assert evaluate_trigger(rank, 10, [1, 2], [1, 2, 3], 3).fired
    # price drop keeping the same position
    assert not evaluate_trigger(rank, 10, [1, 2, 3], [1, 2, 3], 2).fired
    # overtaking
    assert evaluate_trigger(rank, 10, [1, 2, 3], [1, 3, 2], 3).fired


def test_l1_change_definitions():
    l1 = TriggerType.L1_CHANGE
    assert evaluate_trigger(l1, 10, [], [1], 1).fired
    assert not evaluate_trigger(l1, 10, [1, 2], [1, 2, 3], 3).fired  # new entrant not at L1
    assert not evaluate_trigger(l1, 10, [1, 2], [1, 2], 1).fired  # L1 lowers own price
    assert not evaluate_trigger(l1, 10, [1, 2, 3], [1, 3, 2], 3).fired  # change below L1
    assert evaluate_trigger(l1, 10, [1, 2], [2, 1], 2).fired


# ---------- acceptance window ----------

def test_bid_before_start_rejected(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(T0 - timedelta(seconds=1))
    r = place(client, rfq, users["a"], "100.00")
    assert r.status_code == 409
    assert "not started" in r.json()["detail"]


def test_bid_exactly_at_close_rejected(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(CLOSE)
    r = place(client, rfq, users["a"], "100.00")
    assert r.status_code == 409
    assert r.json()["detail"] == "Auction is closed"
    assert "server_now" in r.json()


def test_bid_just_before_close_accepted(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(CLOSE - timedelta(microseconds=1))
    assert place(client, rfq, users["a"], "100.00").status_code == 201


def test_acceptance_uses_time_not_cached_status(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])  # stored status is still UPCOMING
    clock.set(T0 + timedelta(minutes=1))
    assert place(client, rfq, users["a"], "100.00").status_code == 201


# ---------- bid validation ----------

def test_bid_must_be_lower_than_own_previous(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(T0 + timedelta(minutes=1))
    assert place(client, rfq, users["a"], "100.00").status_code == 201
    r = place(client, rfq, users["a"], "100.00")
    assert r.status_code == 422 and "lower than your previous bid" in r.json()["detail"]
    assert place(client, rfq, users["a"], "100.01").status_code == 422
    assert place(client, rfq, users["a"], "99.99").status_code == 201


def test_quote_validity_before_pickup_rejected(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(T0 + timedelta(minutes=1))
    day_before = (rfq.pickup_date - timedelta(days=1)).isoformat()
    r = place(client, rfq, users["a"], "100.00", quote_validity_date=day_before)
    assert r.status_code == 422 and r.json()["field"] == "quote_validity_date"
    ok = place(client, rfq, users["a"], "100.00", quote_validity_date=rfq.pickup_date.isoformat())
    assert ok.status_code == 201


def test_transit_time_must_be_positive(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(T0 + timedelta(minutes=1))
    for days in (0, -1):
        r = place(client, rfq, users["a"], "100.00", transit_time_days=days)
        assert r.status_code == 422


def test_negative_charges_rejected(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(T0 + timedelta(minutes=1))
    assert place(client, rfq, users["a"], "100.00", origin_charges="-1.00").status_code == 422


def test_decimal_precision_is_exact(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(T0 + timedelta(minutes=1))
    r = place(client, rfq, users["a"], "0.10", origin_charges="0.20", destination_charges="0.00")
    assert r.status_code == 201
    assert r.json()["quote"]["total_price"] == "0.30"
    stored = db.scalar(select(Bid.total_price))
    assert stored == Decimal("0.30") and isinstance(stored, Decimal)


def test_only_suppliers_can_bid(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(T0 + timedelta(minutes=1))
    assert place(client, rfq, users["buyer"], "100.00").status_code == 403
    r = client.post(f"/api/rfqs/{rfq.id}/bids", json={})
    assert r.status_code in (401, 422)


# ---------- extensions ----------

def test_any_bid_outside_window_does_not_extend(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(CLOSE - timedelta(minutes=10, microseconds=1))
    assert place(client, rfq, users["a"], "100.00").json()["extension"] is None
    assert close_at(db, rfq) == CLOSE


def test_any_bid_at_window_start_extends(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(CLOSE - timedelta(minutes=10))
    body = place(client, rfq, users["a"], "100.00").json()
    assert body["extension"]["new_close_at"].startswith("2030-01-01T10:35")
    assert close_at(db, rfq) == CLOSE + timedelta(minutes=5)
    log = events(db, rfq, EventType.TIME_EXTENDED)
    assert len(log) == 1 and log[0].old_close_at == CLOSE and "Bid received" in log[0].reason


def test_extension_measured_from_current_close(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(CLOSE - timedelta(minutes=1))
    place(client, rfq, users["a"], "100.00")
    place(client, rfq, users["b"], "90.00")
    assert close_at(db, rfq) == CLOSE + timedelta(minutes=10)


def test_rank_change_first_bid_last_extends(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"], trigger=TriggerType.ANY_RANK_CHANGE)
    clock.set(T0 + timedelta(minutes=1))
    place(client, rfq, users["a"], "100.00")
    place(client, rfq, users["b"], "110.00")
    clock.set(CLOSE - timedelta(minutes=2))
    r = place(client, rfq, users["c"], "120.00")  # lands at L3
    assert r.json()["rank"] == 3
    assert r.json()["extension"] is not None
    assert "new entrant at L3" in r.json()["extension"]["reason"]


def test_rank_change_same_position_does_not_extend(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"], trigger=TriggerType.ANY_RANK_CHANGE)
    clock.set(T0 + timedelta(minutes=1))
    place(client, rfq, users["a"], "100.00")
    place(client, rfq, users["b"], "110.00")
    clock.set(CLOSE - timedelta(minutes=2))
    r = place(client, rfq, users["b"], "105.00")  # still L2
    assert r.json()["rank"] == 2 and r.json()["extension"] is None
    assert close_at(db, rfq) == CLOSE


def test_rank_change_overtake_extends(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"], trigger=TriggerType.ANY_RANK_CHANGE)
    clock.set(T0 + timedelta(minutes=1))
    place(client, rfq, users["a"], "100.00")
    place(client, rfq, users["b"], "110.00")
    clock.set(CLOSE - timedelta(minutes=2))
    r = place(client, rfq, users["b"], "99.00")
    assert r.json()["rank"] == 1
    assert "moved from L2 to L1" in r.json()["extension"]["reason"]


def test_tie_keeps_earlier_bidder_ahead(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"], trigger=TriggerType.ANY_RANK_CHANGE)
    clock.set(T0 + timedelta(minutes=1))
    place(client, rfq, users["a"], "100.00")
    place(client, rfq, users["b"], "110.00")
    clock.set(CLOSE - timedelta(minutes=2))
    r = place(client, rfq, users["b"], "100.00")  # matches L1 but A was first
    assert r.json()["rank"] == 2 and r.json()["extension"] is None


def test_l1_change_only(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"], trigger=TriggerType.L1_CHANGE)
    clock.set(T0 + timedelta(minutes=1))
    place(client, rfq, users["a"], "100.00")
    place(client, rfq, users["b"], "110.00")
    clock.set(CLOSE - timedelta(minutes=3))
    assert place(client, rfq, users["c"], "105.00").json()["extension"] is None  # L2, not L1
    assert place(client, rfq, users["a"], "95.00").json()["extension"] is None  # L1 lowers own price
    r = place(client, rfq, users["b"], "94.00")
    assert r.json()["extension"] is not None
    assert close_at(db, rfq) == CLOSE + timedelta(minutes=5)


def test_extension_capped_then_force_closed(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"], close=CLOSE, forced=CLOSE + timedelta(minutes=7))
    clock.set(CLOSE - timedelta(minutes=1))
    place(client, rfq, users["a"], "100.00")  # +5 -> close+5
    r = place(client, rfq, users["b"], "99.00")  # +5 wanted, only +2 left
    ext = r.json()["extension"]
    assert ext["capped"] is True and "cap reached" in ext["reason"]
    assert close_at(db, rfq) == rfq.forced_close_at

    # repeated triggers after the cap: no further extension, exactly one EXTENSION_CAPPED
    for i, who in enumerate(["c", "a", "b", "c"]):
        assert place(client, rfq, users[who], str(98 - i) + ".00").json()["extension"] is None
    capped = events(db, rfq, EventType.EXTENSION_CAPPED)
    assert len(capped) == 1
    assert close_at(db, rfq) == rfq.forced_close_at
    # The cap entry comes after the bid that triggered it.
    bid_entry = db.scalar(select(ActivityLog).where(
        ActivityLog.bid_id == capped[0].bid_id, ActivityLog.event_type == EventType.BID_SUBMITTED))
    assert bid_entry.id < capped[0].id

    clock.set(rfq.forced_close_at)
    assert place(client, rfq, users["a"], "1.00").status_code == 409
    detail = client.get(f"/api/rfqs/{rfq.id}", headers=as_user(users["buyer"])).json()
    assert detail["rfq"]["status"] == "FORCE_CLOSED"
    assert db.scalar(select(func.count()).select_from(ActivityLog).where(
        ActivityLog.rfq_id == rfq.id, ActivityLog.event_type == EventType.FORCE_CLOSED)) == 1


def test_normal_close_status(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"])
    clock.set(T0 + timedelta(minutes=1))
    place(client, rfq, users["a"], "100.00")
    clock.set(CLOSE)
    detail = client.get(f"/api/rfqs/{rfq.id}", headers=as_user(users["buyer"])).json()
    assert detail["rfq"]["status"] == "CLOSED"
    assert detail["server_now"].startswith("2030-01-01T10:30")
