"""Paths and corridor constants."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DB_PATH = REPO_ROOT / "fishfinder.db"

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

ZONES_PATH = DATA_DIR / "zones.geojson"
PORTS_PATH = DATA_DIR / "ports.json"
SPECIES_PATH = DATA_DIR / "species.json"
SPECIES_PROFILES_PATH = DATA_DIR / "species_profiles.json"

CORRIDOR = "south_florida"
