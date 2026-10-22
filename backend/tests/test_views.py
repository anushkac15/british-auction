import json
from datetime import timedelta

from app.enums import Role, TriggerType
from app.models import User
from tests.conftest import T0, as_user, make_rfq, place

CLOSE = T0 + timedelta(minutes=30)


def _setup(client, clock, db, users):
    rfq = make_rfq(db, users["buyer"], trigger=TriggerType.ANY_RANK_CHANGE)
    clock.set(T0 + timedelta(minutes=1))
    place(client, rfq, users["a"], "1111.11", carrier_name="AlphaCarrier")
    place(client, rfq, users["b"], "2222.22", carrier_name="BravoCarrier")
    place(client, rfq, users["c"], "3333.33", carrier_name="CharlieCarrier")
    clock.set(CLOSE - timedelta(minutes=1))
    place(client, rfq, users["c"], "1000.00", carrier_name="CharlieCarrier")  # takes L1, extends
    return rfq


def test_buyer_sees_everything(client, clock, db, users):
    rfq = _setup(client, clock, db, users)
    body = client.get(f"/api/rfqs/{rfq.id}", headers=as_user(users["buyer"])).json()["rfq"]
    assert [r["supplier_name"] for r in body["ranking"]] == ["Supplier Charlie", "Supplier Alpha", "Supplier Bravo"]
    assert [r["label"] for r in body["ranking"]] == ["L1", "L2", "L3"]
    assert body["ranking"][1]["quote"]["total_price"] == "1111.11"
    assert body["lowest_bid"] == "1000.00"
    assert len(body["bids"]) == 4
    assert body["extension_count"] == 1
    extended = next(a for a in body["activity"] if a["event_type"] == "TIME_EXTENDED")
    assert "Supplier Charlie's bid" in extended["message"]


def test_supplier_sees_only_own_data_and_l1_price(client, clock, db, users):
    rfq = _setup(client, clock, db, users)
    resp = client.get(f"/api/rfqs/{rfq.id}", headers=as_user(users["b"])).json()
    body = resp["rfq"]
    raw = json.dumps(resp)

    assert body["my_rank"] == 3 and body["participant_count"] == 3
    assert body["lowest_bid"] == "1000.00"  # anonymous L1 price is visible
    assert [r["is_me"] for r in body["ranking"]] == [True]
    assert body["ranking"][0]["rank"] == 3
    assert all(b["is_me"] for b in body["bids"])

    for secret in ("Supplier Alpha", "Supplier Charlie", "AlphaCarrier", "CharlieCarrier", "1111.11", "3333.33",
                   "1,111.11", "3,333.33"):
        assert secret not in raw, secret
    assert "A competitor submitted a bid" in raw
    extended = next(a for a in body["activity"] if a["event_type"] == "TIME_EXTENDED")
    assert "a competitor's bid" in extended["message"]


def test_supplier_listing_shows_l1_and_own_rank(client, clock, db, users):
    _setup(client, clock, db, users)
    item = client.get("/api/rfqs", headers=as_user(users["a"])).json()["items"][0]
    assert item["lowest_bid"] == "1000.00"
    assert item["my_rank"] == 2 and item["my_best_bid"] == "1111.11"
    buyer_item = client.get("/api/rfqs", headers=as_user(users["buyer"])).json()["items"][0]
    assert buyer_item["my_rank"] is None


def test_buyer_only_sees_own_rfqs(client, clock, db, users):
    rfq = _setup(client, clock, db, users)
    other = User(name="Other Buyer", email="other@test", role=Role.BUYER)
    db.add(other)
    db.commit()
    assert client.get("/api/rfqs", headers=as_user(other)).json()["items"] == []
    r = client.get(f"/api/rfqs/{rfq.id}", headers=as_user(other))
    assert r.status_code == 404 and "Supplier Alpha" not in r.text
    assert len(client.get("/api/rfqs", headers=as_user(users["buyer"])).json()["items"]) == 1


def test_supplier_sees_rfqs_from_every_buyer(client, clock, db, users):
    other = User(name="Other Buyer", email="other@test", role=Role.BUYER)
    db.add(other)
    db.commit()
    make_rfq(db, users["buyer"], ref="MINE")
    make_rfq(db, other, ref="THEIRS")
    clock.set(T0 + timedelta(minutes=31))  # finished auctions stay listed too

    def refs(user):
        return {i["reference_id"] for i in client.get("/api/rfqs", headers=as_user(user)).json()["items"]}

    assert refs(users["a"]) == {"MINE", "THEIRS"}
    assert refs(users["buyer"]) == {"MINE"}
    assert refs(other) == {"THEIRS"}


def test_missing_user_header_is_401(client, users):
    r = client.get("/api/rfqs")
    assert r.status_code == 401 and "server_now" in r.json()


def test_every_response_has_server_now(client, clock, users):
    assert client.get("/api/health").json()["server_now"].startswith("2030-01-01T10:00")
    assert "server_now" in client.get("/api/rfqs", headers=as_user(users["buyer"])).json()
