import pytest

from pipeline.load import ENTITY_BY_API, ensure_schema, get_watermark, lookback, set_watermark, upsert


def customer(i, modified="2026-01-01T09:00:00Z", **extra):
    row = {"id": f"id-{i}", "number": f"C{i}", "displayName": f"Customer {i}", "type": "Company",
           "city": "Addis Ababa", "country": "ET", "email": f"c{i}@example.com", "lastModifiedDateTime": modified}
    row.update(extra)
    return row


def test_upsert_is_idempotent(wh):
    ensure_schema(wh)
    entity = ENTITY_BY_API["customers"]
    upsert(wh, entity, [customer(1), customer(2)])
    upsert(wh, entity, [customer(1), customer(2)])
    assert wh.query("SELECT COUNT(*) FROM raw_customers")[0][0] == 2


def test_upsert_updates_changed_records(wh):
    ensure_schema(wh)
    entity = ENTITY_BY_API["customers"]
    upsert(wh, entity, [customer(1)])
    rows, newest = upsert(wh, entity, [customer(1, modified="2026-02-01T10:00:00Z", city="Nairobi")])
    assert rows == 1 and newest == "2026-02-01T10:00:00Z"
    assert wh.query("SELECT city FROM raw_customers WHERE id = 'id-1'")[0][0] == "Nairobi"


def test_upsert_rejects_records_missing_fields(wh):
    ensure_schema(wh)
    bad = customer(1)
    del bad["email"]
    with pytest.raises(ValueError, match="email"):
        upsert(wh, ENTITY_BY_API["customers"], [bad])


def test_watermark_round_trip_keeps_old_value_when_nothing_new(wh):
    ensure_schema(wh)
    entity = ENTITY_BY_API["customers"]
    set_watermark(wh, entity, "2026-03-01T00:00:00Z", 5)
    set_watermark(wh, entity, None, 0)  # empty incremental run
    assert get_watermark(wh, entity) == "2026-03-01T00:00:00Z"


def test_lookback_steps_back():
    assert lookback("2026-03-01T00:05:00Z", 10) == "2026-02-28T23:55:00Z"
    assert lookback(None, 10) is None
