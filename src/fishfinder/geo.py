"""Geospatial helpers: haversine range + nearest-point. Reused by the Phase 2 range filter."""

import json
import math
from pathlib import Path

from . import config

EARTH_RADIUS_NM = 3440.065  # nautical miles


def haversine_nm(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in nautical miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def nearest(lat: float, lng: float, points: list[dict]) -> tuple[dict, float]:
    """Return (point, distance_nm) for the closest point. Each point needs 'lat'/'lng'.

    Raises ValueError on an empty list so a mis-wired station catalog fails loudly rather
    than silently returning no data.
    """
    if not points:
        raise ValueError("nearest() called with no points")
    best, best_d = None, math.inf
    for pt in points:
        d = haversine_nm(lat, lng, pt["lat"], pt["lng"])
        if d < best_d:
            best, best_d = pt, d
    return best, best_d


def load_zones(path: Path | None = None) -> list[dict]:
    """Load the zone catalog as flat dicts: {zone_id, name, lat, lng, depth_ft, structure}."""
    geo = json.loads((path or config.ZONES_PATH).read_text())
    zones = []
    for f in geo["features"]:
        lng, lat = f["geometry"]["coordinates"]  # GeoJSON order is [lng, lat]
        props = f["properties"]
        zones.append(
            {
                "zone_id": props["zone_id"],
                "name": props.get("name"),
                "lat": lat,
                "lng": lng,
                "depth_ft": props.get("depth_ft"),
                "structure": props.get("structure", []),
            }
        )
    return zones
