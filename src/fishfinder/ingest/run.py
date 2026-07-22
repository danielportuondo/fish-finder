"""Ingestion orchestrator: pull every §7 source, resolve to zones, write zone_conditions.

  uv run python -m fishfinder.ingest.run [--date YYYY-MM-DD] [--db PATH]

DoD (HANDOFF §10): one command populates today's conditions for every zone; re-runs are
idempotent (upsert on zone_id+observed_at); missing/cloudy data never crashes it.
"""

import argparse
import json
import sqlite3
from datetime import date as date_cls
from datetime import datetime, timezone

from .. import config, db, geo
from . import astro
from .sources import SOURCES

# For overlapping columns, the first source that resolves a non-null value wins.
PRECEDENCE = {
    "sst_f": ["coastwatch", "open_meteo", "ndbc"],
    "sst_break_gradient": ["coastwatch"],
    "chlorophyll": ["coastwatch"],
    "dist_to_stream_edge_nm": ["coastwatch"],
    "wave_height_ft": ["open_meteo", "ndbc"],
    "wind_speed_kt": ["open_meteo", "ndbc"],
    "wind_dir_deg": ["open_meteo", "ndbc"],
    "pressure_mb": ["open_meteo", "ndbc"],
    "pressure_trend_3h": ["open_meteo"],
    "current_speed_kt": ["co_ops"],
    "current_dir_deg": ["co_ops"],
    "tide_state": ["co_ops"],
}
ASTRO_COLUMNS = ["moon_illumination", "solunar_score"]
FEATURE_COLUMNS = list(PRECEDENCE) + ASTRO_COLUMNS

# dist_to_stream_edge_nm is a coarse SST-gradient proxy; currents are not wired (see co_ops).
COARSE_COLUMNS = {"dist_to_stream_edge_nm"}
UNWIRED_COLUMNS = {"current_speed_kt", "current_dir_deg"}


def collect(zones: list[dict], date: str) -> dict[str, dict[str, dict]]:
    """Run every source; a source that raises degrades to {} so one dead feed can't crash
    the run. Returns {source_name: {zone_id: {col: val}}}."""
    per_source = {}
    for module in SOURCES:
        try:
            per_source[module.NAME] = module.fetch(zones, date) or {}
        except Exception:  # belt-and-suspenders; sources already swallow their own errors
            per_source[module.NAME] = {}
    return per_source


def merge_zone(zone_id: str, date: str, per_source: dict) -> tuple[dict, dict]:
    """Resolve one zone's feature vector by precedence + local astro. Returns
    (features, source_meta)."""
    features = {}
    contributed: dict[str, list] = {}
    for col, order in PRECEDENCE.items():
        for name in order:
            val = per_source.get(name, {}).get(zone_id, {}).get(col)
            if val is not None:
                features[col] = val
                contributed.setdefault(name, []).append(col)
                break

    features["moon_illumination"] = round(astro.moon_illumination(date), 4)
    features["solunar_score"] = round(astro.solunar_score(date), 4)
    contributed["astro"] = list(ASTRO_COLUMNS)

    resolved = sorted(c for c in FEATURE_COLUMNS if features.get(c) is not None)
    gaps = sorted(c for c in FEATURE_COLUMNS if features.get(c) is None)
    notes = []
    if "dist_to_stream_edge_nm" in resolved:
        notes.append("dist_to_stream_edge_nm is a coarse SST-gradient proxy")
    if UNWIRED_COLUMNS & set(gaps):
        notes.append("currents not wired (offshore CO-OPS current stations sparse)")
    source_meta = {
        "resolved": resolved,
        "gaps": gaps,
        "sources": {k: sorted(v) for k, v in contributed.items()},
        "notes": notes,
    }
    return features, source_meta


def write_conditions(
    conn: sqlite3.Connection, zone_id: str, observed_at: str, features: dict, source_meta: dict
) -> None:
    """Idempotent upsert of one zone_conditions row (unique on zone_id+observed_at)."""
    cols = ["zone_id", "observed_at", *FEATURE_COLUMNS, "source_meta"]
    params = {
        "zone_id": zone_id,
        "observed_at": observed_at,
        "source_meta": json.dumps(source_meta),
        **{c: features.get(c) for c in FEATURE_COLUMNS},
    }
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in (*FEATURE_COLUMNS, "source_meta"))
    conn.execute(
        f"INSERT INTO zone_conditions ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(zone_id, observed_at) DO UPDATE SET {updates}",
        params,
    )


def ingest(conn: sqlite3.Connection, date: str) -> dict:
    """Full pipeline for one date. Returns a summary dict (also used by tests)."""
    zones = geo.load_zones()
    observed_at = f"{date}T00:00:00Z"
    per_source = collect(zones, date)

    col_counts = dict.fromkeys(FEATURE_COLUMNS, 0)
    for z in zones:
        features, source_meta = merge_zone(z["zone_id"], date, per_source)
        write_conditions(conn, z["zone_id"], observed_at, features, source_meta)
        for c in FEATURE_COLUMNS:
            if features.get(c) is not None:
                col_counts[c] += 1
    conn.commit()
    return {"zones": len(zones), "observed_at": observed_at, "col_counts": col_counts}


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate zone_conditions from §7 feeds.")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    # Validate date early so a typo fails loudly, not mid-ingest.
    date_cls.fromisoformat(args.date)

    conn = db.connect(args.db or config.DB_PATH)
    try:
        db.init_db(conn)
        summary = ingest(conn, args.date)
    finally:
        conn.close()

    n = summary["zones"]
    print(f"Ingested {n} zones @ {summary['observed_at']}")
    for col, cnt in summary["col_counts"].items():
        flag = ""
        if col in COARSE_COLUMNS:
            flag = " (coarse)"
        elif col in UNWIRED_COLUMNS:
            flag = " (not wired)"
        print(f"  {col:<24} {cnt}/{n}{flag}")


if __name__ == "__main__":
    main()
