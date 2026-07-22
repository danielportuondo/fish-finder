"""Catch logging: full snapshot, incomplete flag (never drop), skunked, error paths."""

import json

import pytest

from fishfinder import catchlog, db, recommend, seed

DATE = "2026-07-22"
OBSERVED_AT = f"{DATE}T00:00:00Z"
ZONE = "SF-HAULOVER-DROP-02"


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


def _insert_conditions(conn, zone_id, **cols):
    keys = ["zone_id", "observed_at", *cols]
    conn.execute(
        f"INSERT INTO zone_conditions ({', '.join(keys)}) "
        f"VALUES ({', '.join(f':{k}' for k in keys)})",
        {"zone_id": zone_id, "observed_at": OBSERVED_AT, **cols},
    )
    conn.commit()


def _row(conn, log_id):
    return conn.execute("SELECT * FROM catch_logs WHERE id = ?", (log_id,)).fetchone()


def test_full_snapshot_when_conditions_exist(conn):
    _insert_conditions(conn, ZONE, sst_f=79.5, dist_to_stream_edge_nm=2.0)
    out = catchlog.log_catch(conn, device_id="d1", zone_id=ZONE, date=DATE, species="mahi", count=3)
    assert out["snapshot_incomplete"] == 0
    assert out["observed_at"] == OBSERVED_AT

    row = _row(conn, out["id"])
    assert row["snapshot_incomplete"] == 0
    assert row["count"] == 3
    snap = json.loads(row["conditions_snapshot"])
    # Snapshot is exactly what the recommendation showed (env + static props).
    features, _ = recommend.zone_features(conn, ZONE, DATE)
    assert snap == features
    assert snap["sst_f"] == 79.5
    assert snap["depth_ft"] is not None  # static prop present


def test_missing_conditions_flags_incomplete_but_saves(conn):
    # No zone_conditions row: never drop the label — save with snapshot_incomplete = 1.
    out = catchlog.log_catch(conn, device_id="d1", zone_id=ZONE, date=DATE, species="mahi")
    assert out["snapshot_incomplete"] == 1
    assert out["observed_at"] is None
    row = _row(conn, out["id"])
    assert row is not None
    assert row["snapshot_incomplete"] == 1
    # Static props still snapshotted even with no environmental data.
    snap = json.loads(row["conditions_snapshot"])
    assert "depth_ft" in snap


def test_skunked_allows_null_species(conn):
    out = catchlog.log_catch(
        conn, device_id="d1", zone_id=ZONE, date=DATE, species=None, outcome="skunked"
    )
    row = _row(conn, out["id"])
    assert row["species_id"] is None
    assert row["outcome"] == "skunked"


def test_unknown_species_raises(conn):
    with pytest.raises(ValueError, match="unknown species"):
        catchlog.log_catch(conn, device_id="d1", zone_id=ZONE, date=DATE, species="grouper")


def test_species_required_unless_skunked(conn):
    with pytest.raises(ValueError, match="species is required"):
        catchlog.log_catch(conn, device_id="d1", zone_id=ZONE, date=DATE, species=None)


def test_bad_outcome_raises(conn):
    with pytest.raises(ValueError, match="invalid outcome"):
        catchlog.log_catch(
            conn, device_id="d1", zone_id=ZONE, date=DATE, species="mahi", outcome="maybe"
        )


def test_caught_at_defaults_to_date(conn):
    out = catchlog.log_catch(conn, device_id="d1", zone_id=ZONE, date=DATE, species="mahi")
    assert _row(conn, out["id"])["caught_at"] == f"{DATE}T12:00:00Z"
