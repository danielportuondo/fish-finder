"""Recommendation pipeline (HANDOFF §8): range filter → load conditions → score → rank.

Pure Python + SQLite; no web framework import so it stays portable (Cloudflare Pages Function
later). Unknown port/species raise ValueError so the HTTP layer can map them to 400.
"""

import json
import sqlite3

from . import geo
from . import scorer as scorer_mod

# zone_conditions columns that are not part of the scorable feature vector.
_NON_FEATURE_COLS = {"id", "zone_id", "observed_at", "source_meta"}


def _load_port(conn: sqlite3.Connection, code: str) -> dict:
    row = conn.execute("SELECT code, name, lat, lng FROM ports WHERE code = ?", (code,)).fetchone()
    if row is None:
        raise ValueError(f"unknown port: {code!r}")
    return dict(row)


def _load_profile(conn: sqlite3.Connection, species: str) -> dict:
    row = conn.execute(
        "SELECT sp.params FROM species_profiles sp "
        "JOIN species s ON s.id = sp.species_id "
        "WHERE s.code = ? AND sp.active = 1",
        (species,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown species or no active profile: {species!r}")
    return json.loads(row["params"])


def _load_conditions(conn: sqlite3.Connection, zone_id: str, date: str) -> tuple[dict, str | None]:
    """Latest conditions row for the zone on or before ``date``. Returns (features, observed_at).

    Matches the daily bucket ingest writes (f"{date}T00:00:00Z") and falls back to the most
    recent earlier pull if today's is missing."""
    row = conn.execute(
        "SELECT * FROM zone_conditions WHERE zone_id = ? AND observed_at <= ? "
        "ORDER BY observed_at DESC LIMIT 1",
        (zone_id, f"{date}T23:59:59Z"),
    ).fetchone()
    if row is None:
        return {}, None
    features = {k: row[k] for k in row.keys() if k not in _NON_FEATURE_COLS}
    return features, row["observed_at"]


def recommend(
    conn: sqlite3.Connection,
    port: str,
    range_nm: float,
    species: str,
    date: str,
    top_n: int = 10,
) -> dict:
    """Rank reachable zones for one species on ``date``. Every result carries reasons."""
    port_row = _load_port(conn, port)
    profile = _load_profile(conn, species)

    results = []
    for zone in geo.load_zones():
        dist = geo.haversine_nm(port_row["lat"], port_row["lng"], zone["lat"], zone["lng"])
        if dist > range_nm:
            continue
        features, observed_at = _load_conditions(conn, zone["zone_id"], date)
        features = {**features, "depth_ft": zone["depth_ft"], "structure": zone["structure"]}
        value, reasons = scorer_mod.score(features, profile)
        results.append(
            {
                "zone_id": zone["zone_id"],
                "name": zone["name"],
                "distance_nm": round(dist, 1),
                "depth_ft": zone["depth_ft"],
                "score": value,
                "reasons": reasons,
                "observed_at": observed_at,
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return {
        "query": {
            "port": port_row["code"],
            "port_name": port_row["name"],
            "range_nm": range_nm,
            "species": species,
            "date": date,
        },
        "results": results[:top_n],
    }
