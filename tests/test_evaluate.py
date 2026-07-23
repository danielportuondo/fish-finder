"""The gate — the real Phase 5 deliverable. Both directions: promote vs rules-stay-champion."""

from fishfinder import evaluate

# A rules profile whose signals are constant across the fixture below, so the rule scorer cannot
# separate the classes (AUC ≈ 0.5). The model, which sees the driving feature, should beat it.
RULES_PROFILE = {"sst_optimal_f": [78, 82], "depth_ft": [100, 200]}
FEATURE_NAMES = ["wind_speed_kt", "sst_f", "depth_ft"]


def _separable(n=20):
    """label ~ wind_speed_kt; sst/depth held constant (invisible to the rules). Dates interleave
    so the most-recent held-out split still contains both classes."""
    feats, y, caught_at = [], [], []
    for i in range(n):
        label = i % 2
        feats.append({"wind_speed_kt": 30.0 if label else 5.0, "sst_f": 80.0, "depth_ft": 150.0})
        y.append(label)
        caught_at.append(f"2026-01-{i + 1:02d}T12:00:00Z")
    return feats, y, caught_at


def test_gate_promotes_when_model_beats_rules():
    feats, y, caught_at = _separable()
    report = evaluate.holdout_report(feats, y, caught_at, FEATURE_NAMES, RULES_PROFILE)
    assert report["promote"] is True
    assert report["model_auc"] >= report["rules_auc"] + evaluate.AUC_MARGIN
    assert "beats rules" in report["reason"]


def test_gate_declines_on_thin_data():
    # 3 caught / 3 skunked — below MIN_PER_CLASS. Rules must remain champion.
    feats, y, caught_at = _separable(n=6)
    report = evaluate.holdout_report(feats, y, caught_at, FEATURE_NAMES, RULES_PROFILE)
    assert report["promote"] is False
    assert "insufficient labels" in report["reason"]
    assert report["graduation_target"] == evaluate.GRADUATION_TARGET


def test_gate_declines_when_model_ties_rules():
    # Both classes plentiful, but the label is pure noise vs every feature → neither separates.
    feats, y, caught_at = [], [], []
    for i in range(20):
        feats.append({"wind_speed_kt": 10.0, "sst_f": 80.0, "depth_ft": 150.0})
        y.append(i % 2)
        caught_at.append(f"2026-01-{i + 1:02d}T12:00:00Z")
    report = evaluate.holdout_report(feats, y, caught_at, FEATURE_NAMES, RULES_PROFILE)
    assert report["promote"] is False
