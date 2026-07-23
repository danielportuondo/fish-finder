"""scoring.resolve — rules by default, promoted model when present; recommend shape unchanged."""

import json

import pytest

from fishfinder import config, db, model, recommend, scoring, seed


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    seed.seed_ports(c)
    seed.seed_species(c)
    seed.seed_species_profiles(c)
    c.commit()
    yield c
    c.close()


def _write_artifact(models_dir, species, promoted):
    art = model.train(
        [{"sst_f": 80.0, "depth_ft": 200.0}, {"sst_f": 70.0, "depth_ft": 60.0}],
        [1, 0],
        ["sst_f", "depth_ft"],
    )
    art["promoted"] = promoted
    (models_dir / f"{species}.json").write_text(json.dumps(art))


def test_resolve_defaults_to_rules(conn):
    score_fn, profile = scoring.resolve(conn, "mahi")
    assert score_fn is scoring.scorer_mod.score
    assert "sst_optimal_f" in profile  # rules profile params


def test_resolve_uses_promoted_model(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    _write_artifact(tmp_path, "mahi", promoted=True)
    score_fn, profile = scoring.resolve(conn, "mahi")
    assert score_fn is model.score
    assert profile["kind"] == "logreg"


def test_resolve_ignores_unpromoted_model(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    _write_artifact(tmp_path, "mahi", promoted=False)
    score_fn, _ = scoring.resolve(conn, "mahi")
    assert score_fn is scoring.scorer_mod.score  # not promoted → rules


def test_resolve_unknown_species_raises(conn):
    with pytest.raises(ValueError, match="unknown species"):
        scoring.resolve(conn, "grouper")


def test_recommend_shape_unchanged_with_promoted_model(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    _write_artifact(tmp_path, "mahi", promoted=True)
    out = recommend.recommend(conn, "haulover", 30, "mahi", "2026-07-22")
    assert out["results"]
    assert all(r["reasons"] for r in out["results"])
    assert all(isinstance(r["score"], float) for r in out["results"])
