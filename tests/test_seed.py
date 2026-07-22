import json

import pytest

from fishfinder import config, db, seed


@pytest.fixture
def seeded():
    c = db.connect(":memory:")
    db.init_db(c)
    seed.seed_ports(c)
    seed.seed_species(c)
    seed.seed_species_profiles(c)
    c.commit()
    yield c
    c.close()


def test_row_counts(seeded):
    assert seeded.execute("SELECT COUNT(*) n FROM ports").fetchone()["n"] == 3
    assert seeded.execute("SELECT COUNT(*) n FROM species").fetchone()["n"] == 4
    assert seed.zone_count() == 12


def test_exactly_one_active_profile_per_species(seeded):
    rows = seeded.execute(
        "SELECT species_id, COUNT(*) n FROM species_profiles WHERE active = 1 GROUP BY species_id"
    ).fetchall()
    assert len(rows) == 4
    assert all(r["n"] == 1 for r in rows)


def test_every_species_has_active_profile(seeded):
    rows = seeded.execute(
        "SELECT s.code FROM species s "
        "JOIN species_profiles p ON p.species_id = s.id AND p.active = 1"
    ).fetchall()
    assert {r["code"] for r in rows} == {"mahi", "sailfish", "kingfish", "wahoo"}


def test_profile_params_are_valid_json(seeded):
    for r in seeded.execute("SELECT params FROM species_profiles"):
        params = json.loads(r["params"])
        assert "sst_optimal_f" in params
        assert "prefers_structure" in params


def test_seed_is_idempotent(seeded):
    seed.seed_ports(seeded)
    seed.seed_species(seeded)
    seed.seed_species_profiles(seeded)
    seeded.commit()
    assert seeded.execute("SELECT COUNT(*) n FROM ports").fetchone()["n"] == 3
    assert seeded.execute("SELECT COUNT(*) n FROM species_profiles").fetchone()["n"] == 4


def test_zones_geojson_wellformed():
    geo = json.loads(config.ZONES_PATH.read_text())
    assert geo["type"] == "FeatureCollection"
    ids = [f["properties"]["zone_id"] for f in geo["features"]]
    assert len(ids) == len(set(ids)), "zone_ids must be unique"
    for f in geo["features"]:
        assert f["geometry"]["type"] == "Point"
        lng, lat = f["geometry"]["coordinates"]
        assert -81 < lng < -79 and 24 < lat < 26, f"{f['properties']['zone_id']} off-corridor"
