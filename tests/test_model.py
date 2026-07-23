"""Logistic regression: learns a separable signal, obeys the score(features, profile) contract."""

from fishfinder import model


def _separable(n=20):
    """Label driven cleanly by wind_speed_kt; depth is noise. Returns (feature_dicts, y, names)."""
    feature_dicts, y = [], []
    for i in range(n):
        label = i % 2
        feature_dicts.append({"wind_speed_kt": 30.0 if label else 5.0, "depth_ft": 150.0})
        y.append(label)
    return feature_dicts, y, ["wind_speed_kt", "depth_ft"]


def test_train_returns_json_ready_artifact():
    feature_dicts, y, names = _separable()
    art = model.train(feature_dicts, y, names)
    assert art["feature_names"] == names
    assert set(art) >= {"means", "stds", "coef", "intercept", "n_pos", "n_neg"}
    assert art["n_pos"] == 10 and art["n_neg"] == 10


def test_score_obeys_contract():
    feature_dicts, y, names = _separable()
    art = model.train(feature_dicts, y, names)
    value, reasons = model.score({"wind_speed_kt": 30.0, "depth_ft": 150.0}, art)
    assert isinstance(value, float) and 0.0 <= value <= 100.0
    assert isinstance(reasons, list) and reasons and all(isinstance(r, str) for r in reasons)


def test_score_is_monotonic_in_the_driving_feature():
    feature_dicts, y, names = _separable()
    art = model.train(feature_dicts, y, names)
    hi, _ = model.score({"wind_speed_kt": 30.0, "depth_ft": 150.0}, art)
    lo, _ = model.score({"wind_speed_kt": 5.0, "depth_ft": 150.0}, art)
    assert hi > lo


def test_missing_feature_is_imputed_not_crashed():
    feature_dicts, y, names = _separable()
    art = model.train(feature_dicts, y, names)
    value, reasons = model.score({"depth_ft": 150.0}, art)  # wind missing → imputed with mean
    assert 0.0 <= value <= 100.0 and reasons
