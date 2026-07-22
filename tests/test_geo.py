import pytest

from fishfinder import geo


def test_haversine_known_distance():
    # Haulover Inlet -> Government Cut is ~8.2 nm.
    d = geo.haversine_nm(25.9026, -80.1206, 25.7657, -80.1300)
    assert 7.5 < d < 9.0


def test_haversine_zero():
    assert geo.haversine_nm(25.0, -80.0, 25.0, -80.0) == pytest.approx(0.0, abs=1e-9)


def test_nearest_picks_closest():
    pts = [
        {"id": "far", "lat": 28.5, "lng": -80.2},
        {"id": "near", "lat": 25.91, "lng": -80.05},
    ]
    pt, d = geo.nearest(25.90, -80.048, pts)
    assert pt["id"] == "near"
    assert d < 2.0


def test_nearest_empty_raises():
    with pytest.raises(ValueError):
        geo.nearest(25.9, -80.0, [])


def test_load_zones_shape():
    zones = geo.load_zones()
    assert len(zones) == 12
    z = zones[0]
    assert {"zone_id", "lat", "lng", "depth_ft", "structure"} <= z.keys()
    # GeoJSON is [lng, lat]; ensure we did not swap them.
    assert 24 < z["lat"] < 26 and -81 < z["lng"] < -79
