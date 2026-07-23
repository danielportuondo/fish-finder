"""Build a per-species training set from the label table (HANDOFF §10 Phase 5).

Each ``catch_logs`` row is a labeled example: its ``conditions_snapshot`` (the exact feature vector
the recommendation showed) plus an outcome. Positives are ``caught`` rows for the species; negatives
are ``skunked`` rows on a trip that *targeted* the species — the honest, hard-won negative label.

Feature vector = the numeric env columns (``run.FEATURE_COLUMNS``) + static ``depth_ft``.
``structure`` (a categorical tag list) is deferred from the v1 model to keep it simple and honest.
Snapshots are kept even when flagged incomplete — the model imputes gaps; only a truly empty
snapshot is dropped (it carries no signal).
"""

import json
import sqlite3

from .ingest.run import FEATURE_COLUMNS

MODEL_FEATURES: list[str] = [*FEATURE_COLUMNS, "depth_ft"]


def _parse(snapshot: str | None) -> dict | None:
    if not snapshot:
        return None
    features = json.loads(snapshot)
    # A snapshot with no usable numeric feature carries no signal; drop it.
    if not any(features.get(c) is not None for c in MODEL_FEATURES):
        return None
    return features


def build(
    conn: sqlite3.Connection, species_code: str
) -> tuple[list[dict], list[int], list[str], list[str]]:
    """Return (feature_dicts, y, caught_at, feature_names) for one species.

    ``y`` is 1 for a caught label, 0 for a targeted-but-skunked label. Rows are returned in no
    particular order; the eval harness sorts by ``caught_at`` for the time-based split.
    """
    feature_dicts: list[dict] = []
    y: list[int] = []
    caught_at: list[str] = []

    positives = conn.execute(
        "SELECT cl.conditions_snapshot AS snap, cl.caught_at AS caught_at "
        "FROM catch_logs cl JOIN species s ON s.id = cl.species_id "
        "WHERE s.code = ? AND cl.outcome = 'caught'",
        (species_code,),
    ).fetchall()
    for row in positives:
        features = _parse(row["snap"])
        if features is None:
            continue
        feature_dicts.append(features)
        y.append(1)
        caught_at.append(row["caught_at"])

    # Negatives: skunked zones on a trip that targeted this species. target_species is a JSON array;
    # filter in Python so we don't depend on the SQLite json1 extension (stays Cloudflare-portable).
    negatives = conn.execute(
        "SELECT cl.conditions_snapshot AS snap, cl.caught_at AS caught_at, "
        "       t.target_species AS targets "
        "FROM catch_logs cl JOIN trips t ON t.id = cl.trip_id "
        "WHERE cl.outcome = 'skunked'",
    ).fetchall()
    for row in negatives:
        targets = json.loads(row["targets"] or "[]")
        if species_code not in targets:
            continue
        features = _parse(row["snap"])
        if features is None:
            continue
        feature_dicts.append(features)
        y.append(0)
        caught_at.append(row["caught_at"])

    return feature_dicts, y, caught_at, MODEL_FEATURES
