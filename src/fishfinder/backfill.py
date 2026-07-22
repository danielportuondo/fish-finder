"""One-off backfill of historical catch reports into labeled rows (HANDOFF §2.4, §10 Phase 4).

Reads a curated CSV of past South Florida reports, reconstructs each report's conditions from
*historical* free feeds, and writes them as catch_logs labels — seeding the label table before any
live trips exist.

  uv run python -m fishfinder.backfill --reports data/reports_seed.csv [--db PATH]

The live ingest sources fetch only the latest data; this module builds date-anchored URLs for the
same feeds and reuses their parsers + run.merge_zone (precedence, astro, source_meta), so a backfilled
snapshot is shaped identically to a live one. Report *text* parsing (LLM) is deferred (§11): the input
is already structured. Currents/tide_state stay gaps (unwired in live ingest too). Never drops a
label — an unresolved snapshot is flagged, not skipped.
"""

import argparse
import csv
import sqlite3
from collections import Counter
from datetime import date as date_cls

from . import catchlog, config, db, geo, seed
from .ingest import http, run
from .ingest.sources import coastwatch, open_meteo

DEVICE_ID = "backfill:reports"

# Open-Meteo historical (ERA5 reanalysis) — same hourly shape as the live forecast/marine feeds,
# so open_meteo.parse_forecast / parse_marine work unchanged.
ARCHIVE_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude={lat}&longitude={lng}&start_date={date}&end_date={date}"
    "&hourly=surface_pressure,wind_speed_10m,wind_direction_10m&timezone=UTC"
)
MARINE_URL = (
    "https://marine-api.open-meteo.com/v1/marine"
    "?latitude={lat}&longitude={lng}&start_date={date}&end_date={date}"
    "&hourly=wave_height,wave_direction,sea_surface_temperature&timezone=UTC"
)
# CoastWatch ERDDAP is time-indexed: select the date instead of the live "(last)".
SST_URL = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.json"
    "?analysed_sst%5B({date}T00:00:00Z)%5D"
    "%5B({lat_min}):3:({lat_max})%5D"
    "%5B({lng_min}):3:({lng_max})%5D"
)
CHL_URL = (
    "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSSQchlaDaily.json"
    "?chlor_a%5B({date}T00:00:00Z)%5D%5B(0.0)%5D%5B({lat})%5D%5B({lng})%5D"
)


def _open_meteo_historical(zone: dict, date: str) -> dict:
    archive = http.get_json(ARCHIVE_URL.format(lat=zone["lat"], lng=zone["lng"], date=date))
    marine = http.get_json(MARINE_URL.format(lat=zone["lat"], lng=zone["lng"], date=date))
    return {**open_meteo.parse_marine(marine, date), **open_meteo.parse_forecast(archive, date)}


def _coastwatch_historical(zone: dict, date: str) -> dict:
    box = http.get_json(
        SST_URL.format(
            date=date,
            lat_min=zone["lat"] - coastwatch.BOX_LAT_PAD,
            lat_max=zone["lat"] + coastwatch.BOX_LAT_PAD,
            lng_min=zone["lng"] - coastwatch.BOX_LNG_WEST,
            lng_max=zone["lng"] + coastwatch.BOX_LNG_EAST,
        )
    )
    chl = http.get_json(CHL_URL.format(date=date, lat=zone["lat"], lng=zone["lng"]))
    return {**coastwatch.parse_sst_box(box, zone), **coastwatch.parse_chl(chl)}


def historical_conditions(zone: dict, date: str) -> tuple[dict, dict]:
    """Reconstruct one zone's feature vector for a past date. Reuses run.merge_zone so precedence,
    astro, and source_meta match a live pull. Sources that fail degrade to gaps (never raise)."""
    per_source = {
        "open_meteo": {zone["zone_id"]: _open_meteo_historical(zone, date)},
        "coastwatch": {zone["zone_id"]: _coastwatch_historical(zone, date)},
    }
    return run.merge_zone(zone["zone_id"], date, per_source)


def _resolve_zone(row: dict, zones: list[dict]) -> dict:
    """A report's zone: explicit zone_id if present, else nearest catalog zone to lat/lng."""
    zone_id = (row.get("zone_id") or "").strip()
    if zone_id:
        zone = next((z for z in zones if z["zone_id"] == zone_id), None)
        if zone is None:
            raise ValueError(f"unknown zone_id: {zone_id!r}")
        return zone
    zone, _ = geo.nearest(float(row["lat"]), float(row["lng"]), zones)
    return zone


def backfill(conn: sqlite3.Connection, reports: list[dict]) -> dict:
    """Write historical conditions + a labeled catch_logs row per report. Returns a summary."""
    zones = geo.load_zones()

    # Reconstruct conditions once per (zone, date), then label every report against it.
    resolved = [(_resolve_zone(r, zones), r) for r in reports]
    conditions_written = 0
    for zone, date in {(z["zone_id"], r["date"]): (z, r["date"]) for z, r in resolved}.values():
        features, source_meta = historical_conditions(zone, date)
        run.write_conditions(conn, zone["zone_id"], f"{date}T00:00:00Z", features, source_meta)
        conditions_written += 1
    conn.commit()

    per_species: Counter = Counter()
    incomplete = 0
    for zone, row in resolved:
        out = catchlog.log_catch(
            conn,
            device_id=DEVICE_ID,
            zone_id=zone["zone_id"],
            date=row["date"],
            species=(row.get("species") or "").strip() or None,
            count=int(row["count"]) if (row.get("count") or "").strip() else None,
            notes=(row.get("notes") or "").strip() or None,
            outcome="caught",
        )
        per_species[out["species"]] += 1
        incomplete += out["snapshot_incomplete"]

    return {
        "reports": len(reports),
        "conditions_written": conditions_written,
        "labels_by_species": dict(per_species),
        "incomplete_snapshots": incomplete,
    }


def load_reports(path) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        date_cls.fromisoformat(r["date"])  # fail loudly on a bad date, not mid-fetch
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical catch reports into labels.")
    parser.add_argument("--reports", default=str(config.DATA_DIR / "reports_seed.csv"))
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    reports = load_reports(args.reports)
    conn = db.connect(args.db or config.DB_PATH)
    try:
        db.init_db(conn)
        seed.seed_species(conn)  # labels need species rows; idempotent on an already-seeded DB
        conn.commit()
        summary = backfill(conn, reports)
    finally:
        conn.close()

    print(f"Backfilled {summary['reports']} reports")
    print(f"  conditions rows written: {summary['conditions_written']}")
    print(f"  incomplete snapshots (flagged, not dropped): {summary['incomplete_snapshots']}")
    for species, n in sorted(summary["labels_by_species"].items(), key=lambda kv: str(kv[0])):
        print(f"  {species or '(skunked)':<12} {n}")


if __name__ == "__main__":
    main()
