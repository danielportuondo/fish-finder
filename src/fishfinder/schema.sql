-- fish-finder schema (SQLite). Zones live in data/zones.geojson, NOT a table.
-- Timestamps are ISO-8601 TEXT. All columns are plain types so a row is trivially
-- serializable to static JSON (Cloudflare D1 / Pages compatibility).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ports (
    id       INTEGER PRIMARY KEY,
    code     TEXT NOT NULL UNIQUE,
    name     TEXT NOT NULL,
    lat      REAL NOT NULL,
    lng      REAL NOT NULL,
    corridor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS species (
    id           INTEGER PRIMARY KEY,
    code         TEXT NOT NULL UNIQUE,   -- mahi | sailfish | kingfish | wahoo
    display_name TEXT NOT NULL
);

-- Versioned habitat rules. params is the domain signature (JSON); the scorer reads it
-- generically and never hardcodes species logic. Exactly one active profile per species.
CREATE TABLE IF NOT EXISTS species_profiles (
    id         INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id),
    version    INTEGER NOT NULL,
    active     INTEGER NOT NULL DEFAULT 0,   -- boolean
    params     TEXT NOT NULL,                -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (species_id, version)
);

-- Enforce at most one active profile per species.
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_profile
    ON species_profiles (species_id) WHERE active = 1;

-- Append-only feature vector per zone per pull. All env columns nullable: score with
-- whatever resolved, note reduced confidence. zone_id is free-text matching the geojson.
CREATE TABLE IF NOT EXISTS zone_conditions (
    id                     INTEGER PRIMARY KEY,
    zone_id                TEXT NOT NULL,
    observed_at            TEXT NOT NULL,
    sst_f                  REAL,
    sst_break_gradient     REAL,
    chlorophyll            REAL,
    current_speed_kt       REAL,
    current_dir_deg        REAL,
    dist_to_stream_edge_nm REAL,
    wave_height_ft         REAL,
    wind_speed_kt          REAL,
    wind_dir_deg           REAL,
    pressure_mb            REAL,
    pressure_trend_3h      REAL,
    moon_illumination      REAL,
    solunar_score          REAL,
    tide_state             TEXT,
    source_meta            TEXT,   -- JSON: which feeds resolved / gaps
    UNIQUE (zone_id, observed_at) -- idempotent ingestion re-runs
);

CREATE INDEX IF NOT EXISTS idx_zone_conditions_lookup
    ON zone_conditions (zone_id, observed_at);

CREATE TABLE IF NOT EXISTS trips (
    id             INTEGER PRIMARY KEY,
    device_id      TEXT NOT NULL,
    port_id        INTEGER REFERENCES ports(id),
    range_nm       REAL,
    target_species TEXT,   -- JSON array
    trip_date      TEXT,
    zones_fished   TEXT,   -- JSON array
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- The crown jewel: the label table. Every log is a labeled training example.
-- species_id is NULLABLE to support skunked/negative rows. Never drop a label:
-- if conditions can't be resolved, still save the row and set snapshot_incomplete = 1.
CREATE TABLE IF NOT EXISTS catch_logs (
    id                  INTEGER PRIMARY KEY,
    device_id           TEXT NOT NULL,
    trip_id             INTEGER REFERENCES trips(id),
    species_id          INTEGER REFERENCES species(id),
    zone_id             TEXT NOT NULL,
    caught_at           TEXT NOT NULL,
    count               INTEGER,
    notes               TEXT,
    outcome             TEXT NOT NULL DEFAULT 'caught'
                        CHECK (outcome IN ('caught', 'skunked')),
    conditions_snapshot TEXT,                 -- JSON feature vector at catch time
    snapshot_incomplete INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_catch_logs_species ON catch_logs (species_id);
