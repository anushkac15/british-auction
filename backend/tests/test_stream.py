import pytest

from app.enums import Role
from app.models import User
from app.routers import stream
from tests.conftest import as_user, make_rfq


@pytest.fixture
def other_buyer(db) -> User:
    user = User(name="Other Buyer", email="other@test", role=Role.BUYER)
    db.add(user)
    db.commit()
    return user


def test_stream_requires_login(client, db, users):
    rfq = make_rfq(db, users["buyer"])
    r = client.get(f"/api/rfqs/{rfq.id}/stream")
    assert r.status_code == 401
    r = client.get(f"/api/rfqs/{rfq.id}/stream", headers={"Authorization": "Bearer forged.token"})
    assert r.status_code == 401


def test_stream_rejects_unknown_rfq(client, users):
    assert client.get("/api/rfqs/999/stream", headers=as_user(users["a"])).status_code == 404


def test_stream_hides_other_buyers_rfqs(client, db, users, other_buyer):
    rfq = make_rfq(db, users["buyer"])
    assert client.get(f"/api/rfqs/{rfq.id}/stream", headers=as_user(other_buyer)).status_code == 404


@pytest.mark.parametrize("who", ["buyer", "a"])
def test_stream_opens_for_owner_and_suppliers(client, db, users, monkeypatch, who):
    monkeypatch.setattr(stream, "KEEPALIVE_SECONDS", 0.05)
    rfq = make_rfq(db, users["buyer"])
    with client.stream("GET", f"/api/rfqs/{rfq.id}/stream", headers=as_user(users[who])) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        first = next(r.iter_lines())
    assert first == "event: ready"
