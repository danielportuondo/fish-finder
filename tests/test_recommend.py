"""Pipeline tests: range filter, conditions lookup, ranking, error paths."""

import pytest

from fishfinder import db, recommend, seed

DATE = "2026-07-22"
OBSERVED_AT = f"{DATE}T00:00:00Z"


def _insert_conditions(conn, zone_id, **cols):
    keys = ["zone_id", "observed_at", *cols]
    placeholders = ", ".join(f":{k}" for k in keys)
    conn.execute(
        f"INSERT INTO zone_conditions ({', '.join(keys)}) VALUES ({placeholders})",
        {"zone_id": zone_id, "observed_at": OBSERVED_AT, **cols},
    )
    conn.commit()


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


def test_range_filter_excludes_far_zones(conn):
    # Haulover → Islamorada zones are ~60+ nm; a 20 nm range must exclude them.
    out = recommend.recommend(conn, "haulover", 20, "mahi", DATE)
    zone_ids = {r["zone_id"] for r in out["results"]}
    assert not any(z.startswith("SF-ISLA") for z in zone_ids)
    assert zone_ids  # some Miami/Haulover zones remain


def test_ranking_prefers_warm_current_edge_for_mahi(conn):
    _insert_conditions(conn, "SF-HAULOVER-DROP-02", sst_f=79.5, dist_to_stream_edge_nm=2.0)
    _insert_conditions(conn, "SF-MIAMI-EDGE-04", sst_f=71.0)
    out = recommend.recommend(conn, "haulover", 20, "mahi", DATE)
    ranked = [r["zone_id"] for r in out["results"]]
    assert ranked.index("SF-HAULOVER-DROP-02") < ranked.index("SF-MIAMI-EDGE-04")


def test_every_result_carries_reasons(conn):
    _insert_conditions(conn, "SF-HAULOVER-DROP-02", sst_f=79.5, dist_to_stream_edge_nm=2.0)
    out = recommend.recommend(conn, "haulover", 20, "mahi", DATE)
    assert out["results"]
    assert all(r["reasons"] for r in out["results"])


def test_top_n_limits_results(conn):
    out = recommend.recommend(conn, "haulover", 100, "mahi", DATE, top_n=3)
    assert len(out["results"]) == 3


def test_unknown_port_raises(conn):
    with pytest.raises(ValueError, match="unknown port"):
        recommend.recommend(conn, "nowhere", 20, "mahi", DATE)


def test_unknown_species_raises(conn):
    with pytest.raises(ValueError, match="unknown species"):
        recommend.recommend(conn, "haulover", 20, "grouper", DATE)


def test_missing_conditions_still_scores_with_static_props(conn):
    # No zone_conditions rows at all: depth/structure still resolve, reasons still returned.
    out = recommend.recommend(conn, "haulover", 20, "mahi", DATE)
    assert out["results"]
    assert all(r["reasons"] for r in out["results"])
