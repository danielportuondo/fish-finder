"""Build fishfinder.db from schema.sql + data/*. Idempotent: safe to re-run."""

import json
import sqlite3
from pathlib import Path

from . import config, db


def _load_json(path: Path):
    return json.loads(path.read_text())


def seed_ports(conn: sqlite3.Connection) -> int:
    ports = _load_json(config.PORTS_PATH)
    for p in ports:
        conn.execute(
            """
            INSERT INTO ports (code, name, lat, lng, corridor)
            VALUES (:code, :name, :lat, :lng, :corridor)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                lat = excluded.lat,
                lng = excluded.lng,
                corridor = excluded.corridor
            """,
            p,
        )
    return len(ports)


def seed_species(conn: sqlite3.Connection) -> int:
    species = _load_json(config.SPECIES_PATH)
    for s in species:
        conn.execute(
            """
            INSERT INTO species (code, display_name)
            VALUES (:code, :display_name)
            ON CONFLICT(code) DO UPDATE SET display_name = excluded.display_name
            """,
            s,
        )
    return len(species)


def seed_species_profiles(conn: sqlite3.Connection) -> int:
    profiles = _load_json(config.SPECIES_PROFILES_PATH)
    code_to_id = {row["code"]: row["id"] for row in conn.execute("SELECT id, code FROM species")}
    for prof in profiles:
        species_id = code_to_id[prof["species_code"]]
        conn.execute(
            """
            INSERT INTO species_profiles (species_id, version, active, params)
            VALUES (:species_id, :version, :active, :params)
            ON CONFLICT(species_id, version) DO UPDATE SET
                active = excluded.active,
                params = excluded.params
            """,
            {
                "species_id": species_id,
                "version": prof["version"],
                "active": 1 if prof.get("active") else 0,
                "params": json.dumps(prof["params"]),
            },
        )
    return len(profiles)


def zone_count() -> int:
    """Zones live in the flat geojson file, not the DB. Report the catalog size."""
    geo = _load_json(config.ZONES_PATH)
    return len(geo["features"])


def main() -> None:
    conn = db.connect()
    try:
        db.init_db(conn)
        n_ports = seed_ports(conn)
        n_species = seed_species(conn)
        n_profiles = seed_species_profiles(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"Seeded {config.DB_PATH.name}:")
    print(f"  ports:            {n_ports}")
    print(f"  species:          {n_species}")
    print(f"  species_profiles: {n_profiles}")
    print(f"  zones (geojson):  {zone_count()}")


if __name__ == "__main__":
    main()
