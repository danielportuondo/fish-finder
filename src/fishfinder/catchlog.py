"""Catch logging (HANDOFF §6): write catch_logs with a full conditions snapshot.

catch_logs is the crown jewel — every log is a labeled training example. Never drop a label: if
conditions can't be resolved for the zone/date, still save the row and flag snapshot_incomplete.

Pure Python + SQLite, no web import (mirrors recommend.py) so the core stays Cloudflare-portable.
Unknown species / bad outcome raise ValueError so the HTTP layer can map them to 400.
"""

import json
import sqlite3

from . import recommend

_OUTCOMES = ("caught", "skunked")


def _resolve_species_id(conn: sqlite3.Connection, species: str) -> int:
    row = conn.execute("SELECT id FROM species WHERE code = ?", (species,)).fetchone()
    if row is None:
        raise ValueError(f"unknown species: {species!r}")
    return row["id"]


def log_catch(
    conn: sqlite3.Connection,
    *,
    device_id: str,
    zone_id: str,
    date: str,
    species: str | None = None,
    count: int | None = None,
    notes: str | None = None,
    outcome: str = "caught",
    caught_at: str | None = None,
    trip_id: int | None = None,
) -> dict:
    """Insert one catch_logs row with a resolved conditions snapshot.

    ``species`` is a species code (None only for a skunked/negative log). ``trip_id`` groups the row
    under a trips row (None for a standalone log). The snapshot is the same feature vector the
    recommendation showed (recommend.zone_features); snapshot_incomplete is set when no environmental
    conditions row resolved.
    """
    if outcome not in _OUTCOMES:
        raise ValueError(f"invalid outcome: {outcome!r} (want one of {_OUTCOMES})")
    if species is None and outcome != "skunked":
        raise ValueError("species is required unless outcome is 'skunked'")

    species_id = _resolve_species_id(conn, species) if species is not None else None
    features, observed_at = recommend.zone_features(conn, zone_id, date)
    snapshot_incomplete = 0 if observed_at is not None else 1
    caught_at = caught_at or f"{date}T12:00:00Z"

    cur = conn.execute(
        "INSERT INTO catch_logs "
        "(device_id, trip_id, species_id, zone_id, caught_at, count, notes, outcome, "
        " conditions_snapshot, snapshot_incomplete) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            device_id,
            trip_id,
            species_id,
            zone_id,
            caught_at,
            count,
            notes,
            outcome,
            json.dumps(features),
            snapshot_incomplete,
        ),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "trip_id": trip_id,
        "zone_id": zone_id,
        "species": species,
        "outcome": outcome,
        "snapshot_incomplete": snapshot_incomplete,
        "observed_at": observed_at,
    }


def _resolve_port_id(conn: sqlite3.Connection, port: str) -> int:
    row = conn.execute("SELECT id FROM ports WHERE code = ?", (port,)).fetchone()
    if row is None:
        raise ValueError(f"unknown port: {port!r}")
    return row["id"]


def log_trip(
    conn: sqlite3.Connection,
    *,
    device_id: str,
    port: str,
    range_nm: float,
    target_species: list[str],
    date: str,
    zones: list[dict],
) -> dict:
    """Record one fishing trip: a trips row plus a catch_logs row per zone fished.

    ``zones`` is a list of ``{zone_id, outcome, species?, count?, notes?}``. A zone with
    ``outcome='skunked'`` becomes a negative label — the thing crowdsourced apps under-collect
    (HANDOFF §2.3). Every row is grouped under the new trip_id and gets a conditions snapshot, so
    negatives are as fully labeled as positives.
    """
    port_id = _resolve_port_id(conn, port)
    cur = conn.execute(
        "INSERT INTO trips (device_id, port_id, range_nm, target_species, trip_date, zones_fished) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            device_id,
            port_id,
            range_nm,
            json.dumps(target_species),
            date,
            json.dumps([z["zone_id"] for z in zones]),
        ),
    )
    trip_id = cur.lastrowid

    logged = [
        log_catch(
            conn,
            device_id=device_id,
            zone_id=z["zone_id"],
            date=date,
            species=z.get("species"),
            count=z.get("count"),
            notes=z.get("notes"),
            outcome=z.get("outcome", "caught"),
            trip_id=trip_id,
        )
        for z in zones
    ]
    conn.commit()  # ensure the trips row persists even when zones is empty
    return {"trip_id": trip_id, "logged": logged}
