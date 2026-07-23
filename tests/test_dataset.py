"""dataset.build: positives from caught rows, negatives from targeted-but-skunked trip zones."""

import json

import pytest

from fishfinder import dataset, db, seed


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    seed.seed_ports(c)
    seed.seed_species(c)
    seed.seed_species_profiles(c)
    c.commit()
    yield c
    c.close()


def _species_id(conn, code):
    return conn.execute("SELECT id FROM species WHERE code = ?", (code,)).fetchone()["id"]


def _insert_catch(conn, *, species_id, outcome, snapshot, caught_at, trip_id=None):
    conn.execute(
        "INSERT INTO catch_logs (device_id, trip_id, species_id, zone_id, caught_at, outcome, "
        " conditions_snapshot) VALUES ('t', ?, ?, 'Z', ?, ?, ?)",
        (trip_id, species_id, caught_at, outcome, json.dumps(snapshot)),
    )
    conn.commit()


def test_positive_from_caught_row(conn):
    _insert_catch(
        conn,
        species_id=_species_id(conn, "mahi"),
        outcome="caught",
        snapshot={"sst_f": 80.0, "depth_ft": 200.0},
        caught_at="2026-06-01T12:00:00Z",
    )
    feats, y, caught_at, names = dataset.build(conn, "mahi")
    assert y == [1]
    assert feats[0]["sst_f"] == 80.0
    assert "depth_ft" in names and "sst_f" in names


def test_negative_from_targeted_skunked_trip(conn):
    conn.execute(
        "INSERT INTO trips (device_id, target_species, trip_date, zones_fished) "
        "VALUES ('t', ?, '2026-06-02', '[\"Z\"]')",
        (json.dumps(["mahi", "wahoo"]),),
    )
    trip_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    _insert_catch(
        conn,
        species_id=None,
        outcome="skunked",
        snapshot={"sst_f": 71.0, "depth_ft": 200.0},
        caught_at="2026-06-02T12:00:00Z",
        trip_id=trip_id,
    )
    feats, y, _, _ = dataset.build(conn, "mahi")
    assert y == [0]  # skunked on a mahi-targeting trip → mahi negative
    # A species not targeted by the trip gets no label from it.
    _, y_king, _, _ = dataset.build(conn, "kingfish")
    assert y_king == []


def test_empty_snapshot_dropped(conn):
    _insert_catch(
        conn,
        species_id=_species_id(conn, "mahi"),
        outcome="caught",
        snapshot={"structure": ["reef"]},  # no numeric model feature → no signal
        caught_at="2026-06-01T12:00:00Z",
    )
    feats, y, _, _ = dataset.build(conn, "mahi")
    assert feats == [] and y == []
