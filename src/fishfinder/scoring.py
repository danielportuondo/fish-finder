"""Scorer dispatch — the hot-swap seam between the rule engine and a trained model (§2 invariant).

``resolve`` picks the active scorer for a species: a promoted model artifact if one exists, else the
rule scorer reading ``species_profiles.params``. Both sides share ``score(features, profile) ->
(score, reasons)``, so the recommendation pipeline never learns which ran. Swapping is reversible by
deleting or un-promoting the artifact — no code change.
"""

import json
import sqlite3
from collections.abc import Callable

from . import config
from . import model as model_mod
from . import scorer as scorer_mod

Scorer = Callable[[dict, dict], tuple[float, list[str]]]


def _load_rules_profile(conn: sqlite3.Connection, species: str) -> dict:
    row = conn.execute(
        "SELECT sp.params FROM species_profiles sp "
        "JOIN species s ON s.id = sp.species_id "
        "WHERE s.code = ? AND sp.active = 1",
        (species,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown species or no active profile: {species!r}")
    return json.loads(row["params"])


def _promoted_model(species: str) -> dict | None:
    path = config.MODELS_DIR / f"{species}.json"
    if not path.exists():
        return None
    artifact = json.loads(path.read_text())
    return artifact if artifact.get("promoted") else None


def resolve(conn: sqlite3.Connection, species: str) -> tuple[Scorer, dict]:
    """Return (score_fn, profile) for the species. Rules are the default and the cold-start fallback;
    a promoted model artifact wins when present. Raises ValueError for an unknown species."""
    rules_profile = _load_rules_profile(conn, species)  # validates species even when a model wins
    artifact = _promoted_model(species)
    if artifact is not None:
        return model_mod.score, artifact
    return scorer_mod.score, rules_profile
