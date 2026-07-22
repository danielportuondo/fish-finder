"""Endpoint tests via FastAPI TestClient. DB path is monkeypatched to a seeded temp file."""

import pytest
from fastapi.testclient import TestClient

from fishfinder import config, db, seed

DATE = "2026-07-22"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    conn = db.connect(db_path)
    db.init_db(conn)
    seed.seed_ports(conn)
    seed.seed_species(conn)
    seed.seed_species_profiles(conn)
    conn.execute(
        "INSERT INTO zone_conditions (zone_id, observed_at, sst_f, dist_to_stream_edge_nm) "
        "VALUES (?, ?, ?, ?)",
        ("SF-HAULOVER-DROP-02", f"{DATE}T00:00:00Z", 79.5, 2.0),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", db_path)
    from fishfinder.server import app

    return TestClient(app)


def test_recommendations_ok(client):
    resp = client.get(f"/recommendations?port=haulover&range_nm=20&species=mahi&date={DATE}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"]["species"] == "mahi"
    assert body["results"]
    assert all(r["reasons"] for r in body["results"])


def test_unknown_species_returns_400(client):
    resp = client.get(f"/recommendations?port=haulover&range_nm=20&species=grouper&date={DATE}")
    assert resp.status_code == 400
    assert "unknown species" in resp.json()["detail"]


def test_missing_required_param_returns_422(client):
    resp = client.get("/recommendations?port=haulover&species=mahi")
    assert resp.status_code == 422  # range_nm required


def test_bad_range_returns_422(client):
    resp = client.get("/recommendations?port=haulover&range_nm=-5&species=mahi")
    assert resp.status_code == 422  # gt=0 constraint
