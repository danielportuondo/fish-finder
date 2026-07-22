"""Backfill: nearest-zone snapping, historical reconstruction (reused parsers + precedence),
labeled rows per species. Fully offline — http.get_json is monkeypatched to fixture payloads."""

import pytest

from fishfinder import backfill, db, geo, seed

DATE = "2024-06-15"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    seed.seed_species(c)
    c.commit()
    yield c
    c.close()


def _hours(**series):
    """An Open-Meteo hourly block: 24 hourly steps so the 12:00 index resolves."""
    times = [f"{DATE}T{h:02d}:00" for h in range(24)]
    return {"hourly": {"time": times, **series}}


def _erddap(rows):
    return {"table": {"rows": rows}}


def _fake_get_json(zone):
    """Route by URL: archive→wind/pressure, marine→wave/sst, ERDDAP SST box, ERDDAP chl."""
    lat, lng = zone["lat"], zone["lng"]

    def get_json(url, timeout=30):
        if "archive-api" in url:
            return _hours(
                surface_pressure=[1015.0] * 24,
                wind_speed_10m=[18.5] * 24,  # km/h
                wind_direction_10m=[90.0] * 24,
            )
        if "marine-api" in url:
            return _hours(wave_height=[0.6] * 24, sea_surface_temperature=[28.0] * 24)
        if "jplMURSST41" in url:
            # A small SST box around the zone (cols: time, lat, lng, sst °C).
            return _erddap(
                [
                    [f"{DATE}T09:00:00Z", lat, lng, 28.0],
                    [f"{DATE}T09:00:00Z", lat + 0.03, lng, 28.4],
                    [f"{DATE}T09:00:00Z", lat, lng + 0.1, 27.0],
                ]
            )
        if "chlaDaily" in url:
            return _erddap([[f"{DATE}T12:00:00Z", 0, lat, lng, 0.12]])
        return None

    return get_json


def test_resolve_zone_snaps_to_nearest():
    zones = geo.load_zones()
    # Just off the Government Cut Sea Buoy (SF-MIAMI-EDGE-04 @ 25.762,-80.092).
    zone = backfill._resolve_zone({"lat": "25.76", "lng": "-80.09"}, zones)
    assert zone["zone_id"] == "SF-MIAMI-EDGE-04"


def test_resolve_zone_explicit_id_wins():
    zones = geo.load_zones()
    zone = backfill._resolve_zone(
        {"lat": "25.76", "lng": "-80.09", "zone_id": "SF-ISLA-HUMP-09"}, zones
    )
    assert zone["zone_id"] == "SF-ISLA-HUMP-09"


def test_resolve_zone_unknown_id_raises():
    with pytest.raises(ValueError, match="unknown zone_id"):
        backfill._resolve_zone({"zone_id": "SF-NOPE-99"}, geo.load_zones())


def test_historical_conditions_reconstructs_and_flags_gaps(monkeypatch):
    zone = next(z for z in geo.load_zones() if z["zone_id"] == "SF-MIAMI-STREAM-06")
    monkeypatch.setattr(backfill.http, "get_json", _fake_get_json(zone))
    features, meta = backfill.historical_conditions(zone, DATE)

    # CoastWatch wins SST precedence; Open-Meteo supplies wave/wind/pressure; astro always resolves.
    assert features["sst_f"] == pytest.approx(82.4, abs=0.1)  # 28.0°C
    assert "wave_height_ft" in features
    assert "wind_speed_kt" in features
    assert "chlorophyll" in features
    assert "moon_illumination" in features and "solunar_score" in features
    # Currents/tide are unwired historically too — they land as gaps, not crashes.
    assert "current_speed_kt" in meta["gaps"]
    assert "tide_state" in meta["gaps"]


def test_backfill_produces_labels_per_species(conn, monkeypatch):
    # One report per species; a shared fake feed for whatever zone each snaps to.
    reports = [
        {
            "date": DATE,
            "species": "mahi",
            "lat": "25.72",
            "lng": "-79.98",
            "count": "4",
            "notes": "",
        },
        {
            "date": DATE,
            "species": "wahoo",
            "lat": "25.80",
            "lng": "-79.90",
            "count": "1",
            "notes": "",
        },
        {
            "date": DATE,
            "species": "sailfish",
            "zone_id": "SF-NMB-LEDGE-03",
            "count": "1",
            "notes": "",
        },
    ]
    monkeypatch.setattr(
        backfill.http,
        "get_json",
        lambda url, timeout=30: _fake_get_json({"lat": 25.8, "lng": -80.0})(url),
    )
    summary = backfill.backfill(conn, reports)

    assert summary["reports"] == 3
    assert summary["labels_by_species"] == {"mahi": 1, "wahoo": 1, "sailfish": 1}
    # A conditions row and a labeled catch row for every report; nothing dropped.
    assert conn.execute("SELECT COUNT(*) FROM catch_logs").fetchone()[0] == 3
    assert (
        conn.execute("SELECT COUNT(*) FROM zone_conditions").fetchone()[0]
        == summary["conditions_written"]
    )
    assert all(
        r["device_id"] == backfill.DEVICE_ID
        for r in conn.execute("SELECT device_id FROM catch_logs")
    )


def test_load_reports_bad_date_raises(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("date,species,lat,lng,count,notes\nnot-a-date,mahi,25.7,-80.0,1,x\n")
    with pytest.raises(ValueError):
        backfill.load_reports(p)
