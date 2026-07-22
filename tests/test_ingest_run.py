"""Orchestrator tests: merge precedence, idempotent upsert, graceful missing data.
Sources are monkeypatched so nothing touches the network."""

import json

import pytest

from fishfinder import db
from fishfinder.ingest import run
from fishfinder.ingest.sources import co_ops, coastwatch, ndbc, open_meteo

DATE = "2026-07-22"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _patch_all(monkeypatch, mapping):
    """mapping: {source_module: fetch_return_dict}."""
    for module in (open_meteo, coastwatch, co_ops, ndbc):
        ret = mapping.get(module, {})
        monkeypatch.setattr(module, "fetch", lambda zones, date, _r=ret: _r)


def test_ingest_writes_every_zone(conn, monkeypatch):
    _patch_all(monkeypatch, {open_meteo: {}})  # all sources empty
    summary = run.ingest(conn, DATE)
    assert summary["zones"] == 12
    rows = conn.execute("SELECT COUNT(*) n FROM zone_conditions").fetchone()["n"]
    assert rows == 12
    # Astro is always computed, so even with no feeds every row has these resolved.
    assert summary["col_counts"]["moon_illumination"] == 12
    assert summary["col_counts"]["solunar_score"] == 12


def test_graceful_missing_flags_gaps_and_survives(conn, monkeypatch):
    _patch_all(monkeypatch, {})  # simulate total feed outage
    run.ingest(conn, DATE)
    row = conn.execute(
        "SELECT sst_f, wave_height_ft, source_meta FROM zone_conditions LIMIT 1"
    ).fetchone()
    assert row["sst_f"] is None
    assert row["wave_height_ft"] is None
    meta = json.loads(row["source_meta"])
    assert "sst_f" in meta["gaps"]
    assert "moon_illumination" in meta["resolved"]


def test_idempotent_rerun(conn, monkeypatch):
    z = "SF-HAULOVER-EDGE-01"
    _patch_all(monkeypatch, {open_meteo: {z: {"wave_height_ft": 2.0, "wind_speed_kt": 10.0}}})
    run.ingest(conn, DATE)
    run.ingest(conn, DATE)  # re-run
    rows = conn.execute("SELECT COUNT(*) n FROM zone_conditions").fetchone()["n"]
    assert rows == 12  # upsert, not append


def test_precedence_coastwatch_sst_wins_over_open_meteo(conn, monkeypatch):
    z = "SF-HAULOVER-EDGE-01"
    _patch_all(
        monkeypatch,
        {
            coastwatch: {z: {"sst_f": 79.0}},
            open_meteo: {z: {"sst_f": 81.0, "wave_height_ft": 2.0}},
            ndbc: {z: {"sst_f": 83.0}},
        },
    )
    run.ingest(conn, DATE)
    row = conn.execute(
        "SELECT sst_f, source_meta FROM zone_conditions WHERE zone_id=?", (z,)
    ).fetchone()
    assert row["sst_f"] == 79.0  # coastwatch precedence
    meta = json.loads(row["source_meta"])
    assert "sst_f" in meta["sources"]["coastwatch"]


def test_ndbc_fills_when_open_meteo_gapped(conn, monkeypatch):
    z = "SF-HAULOVER-EDGE-01"
    _patch_all(
        monkeypatch,
        {open_meteo: {z: {"wave_height_ft": 2.0}}, ndbc: {z: {"wind_speed_kt": 12.0}}},
    )
    run.ingest(conn, DATE)
    row = conn.execute(
        "SELECT wind_speed_kt, source_meta FROM zone_conditions WHERE zone_id=?", (z,)
    ).fetchone()
    assert row["wind_speed_kt"] == 12.0
    meta = json.loads(row["source_meta"])
    assert "wind_speed_kt" in meta["sources"]["ndbc"]
