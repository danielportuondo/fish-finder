"""Offline per-species trainer + promotion report (HANDOFF §10 Phase 5).

  uv run python -m fishfinder.train [--species mahi …] [--db PATH]

For each species: assemble labels (dataset) → evaluate model vs rules on a held-out, time-based split
(evaluate) → refit on all labels → write a ``data/models/{species}.json`` artifact whose ``promoted``
flag is the gate's verdict. The recommendation pipeline reads that flag (scoring.resolve); a
non-promoted artifact leaves the rules as champion. Reproducible: same labels → same report.

Refitting the deployed artifact on *all* labels (after the held-out decision is made) is standard —
the split decides whether to trust the model, the final fit uses every label for the best estimate.
"""

import argparse
import json
import sqlite3

from . import config, db, dataset, evaluate
from . import model as model_mod
from . import scoring, seed


def train_species(conn: sqlite3.Connection, species: str) -> dict:
    """Assemble labels, run the eval gate, and (always) write an artifact with the verdict."""
    feature_dicts, y, caught_at, feature_names = dataset.build(conn, species)
    rules_profile = scoring._load_rules_profile(conn, species)
    report = evaluate.holdout_report(feature_dicts, y, caught_at, feature_names, rules_profile)

    artifact = None
    if len(set(y)) == 2:  # need both classes to fit at all
        artifact = model_mod.train(feature_dicts, y, feature_names)
        artifact["promoted"] = report["promote"]
        artifact["eval"] = report
        config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        (config.MODELS_DIR / f"{species}.json").write_text(json.dumps(artifact, indent=2))

    return {"species": species, "report": report, "wrote_artifact": artifact is not None}


def _fmt_auc(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "n/a"


def main() -> None:
    parser = argparse.ArgumentParser(description="Train per-species models and report vs rules.")
    parser.add_argument("--species", nargs="*", help="species codes; default = all seeded species")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    conn = db.connect(args.db or config.DB_PATH)
    try:
        db.init_db(conn)
        seed.seed_species(conn)  # ensure species rows exist; idempotent
        conn.commit()
        species = args.species or [
            r["code"] for r in conn.execute("SELECT code FROM species ORDER BY code")
        ]
        results = [train_species(conn, s) for s in species]
    finally:
        conn.close()

    print(f"{'species':<10} {'labels':>6} {'pos/neg':>8} {'model':>6} {'rules':>6}  verdict")
    for res in results:
        r = res["report"]
        verdict = "PROMOTE" if r["promote"] else "rules"
        pos_neg = f"{r['n_pos']}/{r['n_neg']}"
        print(
            f"{res['species']:<10} {r['n_labels']:>6} {pos_neg:>8} "
            f"{_fmt_auc(r['model_auc']):>6} {_fmt_auc(r['rules_auc']):>6}  {verdict}"
        )
        print(f"           {r['reason']}")
    promoted = [res["species"] for res in results if res["report"]["promote"]]
    print(f"\nGraduation target: ~{evaluate.GRADUATION_TARGET} labels/species (§2.5).")
    print(f"Promoted this run: {promoted or 'none — rule scorer remains champion'}")


if __name__ == "__main__":
    main()
