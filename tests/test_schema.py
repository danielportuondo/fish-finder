import sqlite3

import pytest

from fishfinder import db

EXPECTED_TABLES = {
    "ports",
    "species",
    "species_profiles",
    "zone_conditions",
    "trips",
    "catch_logs",
}


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def test_all_tables_created(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    assert EXPECTED_TABLES <= names


def test_expected_indexes_exist(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    names = {r["name"] for r in rows}
    assert "idx_one_active_profile" in names
    assert "idx_zone_conditions_lookup" in names
    assert "idx_catch_logs_species" in names


def test_init_db_is_idempotent(conn):
    db.init_db(conn)  # second run must not raise


def test_one_active_profile_per_species_enforced(conn):
    conn.execute("INSERT INTO species (code, display_name) VALUES ('mahi', 'Mahi')")
    sid = conn.execute("SELECT id FROM species WHERE code='mahi'").fetchone()["id"]
    conn.execute(
        "INSERT INTO species_profiles (species_id, version, active, params) VALUES (?, 1, 1, '{}')",
        (sid,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO species_profiles (species_id, version, active, params) "
            "VALUES (?, 2, 1, '{}')",
            (sid,),
        )


def test_catch_log_outcome_check(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO catch_logs (device_id, zone_id, caught_at, outcome) "
            "VALUES ('dev', 'Z1', '2026-07-22T10:00:00', 'bogus')"
        )


def test_catch_log_allows_null_species_for_skunked(conn):
    conn.execute(
        "INSERT INTO catch_logs (device_id, zone_id, caught_at, outcome, species_id) "
        "VALUES ('dev', 'Z1', '2026-07-22T10:00:00', 'skunked', NULL)"
    )
    row = conn.execute("SELECT outcome, species_id FROM catch_logs").fetchone()
    assert row["outcome"] == "skunked"
    assert row["species_id"] is None
