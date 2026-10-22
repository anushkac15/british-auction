import time

import pytest

from app import security
from app.models import User
from app.security import create_token, hash_password, read_token, verify_password
from tests.conftest import as_user


def register(client, **overrides):
    body = {"name": "Fresh Freight", "email": "ops@fresh.test", "password": "s3cret-pass", "role": "SUPPLIER"}
    body.update(overrides)
    return client.post("/api/auth/register", json=body)


def test_password_hash_round_trip():
    stored = hash_password("correct horse")
    assert stored.startswith("scrypt$") and "correct horse" not in stored
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "garbage")


def test_register_returns_token_for_chosen_role(client, db):
    r = register(client, email="  Ops@Fresh.TEST ", role="BUYER")
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["role"] == "BUYER" and body["user"]["email"] == "ops@fresh.test"
    assert "server_now" in body and body["token_type"] == "bearer"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["user"]["id"] == body["user"]["id"]
    stored = db.get(User, body["user"]["id"])
    assert stored.password_hash and "s3cret-pass" not in stored.password_hash


def test_registered_buyer_can_create_rfq_and_supplier_cannot(client):
    buyer = register(client, email="b@new.test", role="BUYER").json()["access_token"]
    supplier = register(client, email="s@new.test", role="SUPPLIER").json()["access_token"]
    assert client.get("/api/rfqs", headers={"Authorization": f"Bearer {buyer}"}).status_code == 200
    r = client.post("/api/rfqs", json={}, headers={"Authorization": f"Bearer {supplier}"})
    assert r.status_code == 403


def test_register_rejects_duplicate_email_case_insensitively(client):
    assert register(client).status_code == 201
    r = register(client, email="OPS@fresh.test")
    assert r.status_code == 409 and r.json()["field"] == "email"


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"email": "not-an-email"}, "email"),
        ({"password": "short"}, "password"),
        ({"name": "   "}, "name"),
        ({"role": "ADMIN"}, "role"),
    ],
)
def test_register_validation(client, overrides, field):
    r = register(client, **overrides)
    assert r.status_code == 422
    assert field in [e["field"] for e in r.json()["errors"]]


def test_login_with_correct_password(client):
    register(client)
    r = client.post("/api/auth/login", json={"email": "OPS@fresh.test", "password": "s3cret-pass"})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Fresh Freight"


@pytest.mark.parametrize("email, password", [("ops@fresh.test", "wrong-pass"), ("nobody@fresh.test", "s3cret-pass")])
def test_login_failure_is_generic(client, email, password):
    register(client)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect email or password"


def test_user_without_password_cannot_log_in(client, users):
    r = client.post("/api/auth/login", json={"email": "buyer@test", "password": "anything"})
    assert r.status_code == 401


def test_tampered_and_expired_tokens_are_rejected(client, users, monkeypatch):
    token = create_token(users["a"].id)
    signature = token.partition(".")[2]
    forged = create_token(users["buyer"].id).partition(".")[0] + "." + signature
    for bad in (forged, token + "x", "not-a-token", ""):
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401
    assert client.get("/api/auth/me", headers={"X-User-Id": str(users["buyer"].id)}).status_code == 401

    assert read_token(token) == users["a"].id
    monkeypatch.setattr(security.time, "time", lambda: time.time_ns() / 1e9 + 13 * 3600)
    assert read_token(token) is None


def test_me_returns_current_user(client, users):
    body = client.get("/api/auth/me", headers=as_user(users["b"])).json()
    assert body["user"] == {"id": users["b"].id, "name": "Supplier Bravo", "email": "b@test", "role": "SUPPLIER"}
