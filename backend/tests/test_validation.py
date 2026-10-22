from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import T0, as_user, make_rfq

START = T0 + timedelta(minutes=5)


def payload(**overrides) -> dict:
    body = {
        "reference_id": "RFQ-100",
        "name": "Chennai to Pune",
        "pickup_date": (T0 + timedelta(days=2)).date().isoformat(),
        "bid_start_at": START.isoformat(),
        "bid_close_at": (START + timedelta(hours=1)).isoformat(),
        "forced_close_at": (START + timedelta(hours=2)).isoformat(),
        "trigger_window_minutes": 10,
        "extension_minutes": 5,
        "trigger_type": "ANY_RANK_CHANGE",
    }
    body.update(overrides)
    return body


def create(client, users, **overrides):
    return client.post("/api/rfqs", json=payload(**overrides), headers=as_user(users["buyer"]))


def test_create_ok(client, users):
    r = create(client, users)
    assert r.status_code == 201, r.text
    rfq = r.json()["rfq"]
    assert rfq["status"] == "UPCOMING"
    assert rfq["bid_close_at"] == rfq["original_bid_close_at"]
    assert rfq["config"] == {"trigger_window_minutes": 10, "extension_minutes": 5, "trigger_type": "ANY_RANK_CHANGE"}
    assert rfq["activity"][0]["event_type"] == "RFQ_CREATED"


def test_times_are_normalised_to_utc(client, users):
    r = create(client, users, bid_start_at="2030-01-01T16:00:00+05:30")  # 10:30 UTC
    assert r.status_code == 201, r.text
    assert r.json()["rfq"]["bid_start_at"].startswith("2030-01-01T10:30:00")


def test_naive_datetimes_rejected(client, users):
    assert create(client, users, bid_start_at="2030-01-01T10:05:00").status_code == 422


def test_start_must_be_in_future(client, users):
    r = create(client, users, bid_start_at=(T0 - timedelta(minutes=1)).isoformat())
    assert r.status_code == 422 and r.json()["field"] == "bid_start_at"


def test_start_grace_for_clock_skew(client, users):
    assert create(client, users, bid_start_at=(T0 - timedelta(seconds=5)).isoformat()).status_code == 201


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"bid_close_at": START.isoformat()}, "Bid close time must be after bid start time"),
        ({"forced_close_at": (START + timedelta(hours=1)).isoformat()}, "Forced close time must be after bid close"),
        ({"pickup_date": T0.date().isoformat(), "forced_close_at": "2030-01-02T01:00:00+00:00"},
         "Pickup date must be on or after the forced close date"),
        ({"bid_close_at": (START + timedelta(minutes=5)).isoformat()}, "Trigger window cannot be longer"),
    ],
)
def test_time_rules(client, users, overrides, message):
    r = create(client, users, **overrides)
    assert r.status_code == 422
    assert message in r.json()["detail"]


def test_pickup_on_forced_close_date_allowed(client, users):
    assert create(client, users, pickup_date=T0.date().isoformat()).status_code == 201


@pytest.mark.parametrize("field, value", [
    ("trigger_window_minutes", 0), ("trigger_window_minutes", 61),
    ("extension_minutes", 0), ("extension_minutes", 61),
])
def test_x_y_bounds(client, users, field, value):
    assert create(client, users, **{field: value}).status_code == 422


def test_duplicate_reference_conflict(client, users):
    assert create(client, users).status_code == 201
    r = create(client, users)
    assert r.status_code == 409


def test_blank_name_rejected(client, users):
    assert create(client, users, name="   ").status_code == 422


def test_only_buyer_can_create(client, users):
    r = client.post("/api/rfqs", json=payload(), headers=as_user(users["a"]))
    assert r.status_code == 403


# ---------- database CHECK constraints back up the API ----------

def test_db_allows_close_equal_to_forced(db, users):
    rfq = make_rfq(db, users["buyer"])
    db.execute(text("UPDATE rfqs SET bid_close_at = forced_close_at WHERE id = :id"), {"id": rfq.id})
    db.commit()


@pytest.mark.parametrize("sql", [
    "UPDATE rfqs SET bid_close_at = forced_close_at + interval '1 second'",
    "UPDATE rfqs SET forced_close_at = original_bid_close_at",
    "UPDATE rfqs SET bid_close_at = original_bid_close_at - interval '1 second'",
    "UPDATE auction_configs SET trigger_window_minutes = 0",
    "UPDATE auction_configs SET extension_minutes = 61",
])
def test_db_rejects_invalid_rows(db, users, sql):
    make_rfq(db, users["buyer"])
    with pytest.raises(IntegrityError):
        db.execute(text(sql))
        db.commit()
    db.rollback()


def test_check_constraint_names_match_models(db):
    names = set(db.scalars(text(
        "SELECT conname FROM pg_constraint WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
    )))
    assert len(names) == 15
    assert not [n for n in names if n.count("ck_") > 1]
    assert {"ck_bids_transit_positive", "ck_rfqs_close_not_after_forced", "ck_users_role"} <= names


def test_db_rejects_bad_bid_rows(db, users):
    rfq = make_rfq(db, users["buyer"])
    insert = text(
        "INSERT INTO bids (rfq_id, supplier_id, carrier_name, freight_charges, origin_charges, "
        "destination_charges, transit_time_days, quote_validity_date, created_at) "
        "VALUES (:rfq, :sup, 'X', :fr, 0, 0, :days, '2031-01-01', now())"
    )
    for fr, days in (("-1", 3), ("1", 0)):
        with pytest.raises(IntegrityError):
            db.execute(insert, {"rfq": rfq.id, "sup": users["a"].id, "fr": fr, "days": days})
            db.commit()
        db.rollback()
