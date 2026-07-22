"""Scorer unit tests: pure function, config-driven, graceful on missing features."""

from fishfinder import scorer

# A mahi-like profile (mirrors data/species_profiles.json shape).
MAHI = {
    "sst_optimal_f": [78, 82],
    "depth_ft": [120, 1000],
    "prefers_structure": ["current_edge", "open", "weedline"],
    "chlorophyll_pref": "break",
    "current_edge_affinity": 0.9,
    "pressure_response": "neutral",
    "weedline_bonus": True,
    "moon_affinity": 0.3,
    "solunar_weight": 0.3,
}


def test_in_band_beats_out_of_band_sst():
    good = {"sst_f": 80.0, "depth_ft": 400, "structure": ["current_edge"]}
    bad = {"sst_f": 60.0, "depth_ft": 400, "structure": ["current_edge"]}
    s_good, _ = scorer.score(good, MAHI)
    s_bad, _ = scorer.score(bad, MAHI)
    assert s_good > s_bad


def test_sst_in_band_reason_and_full_credit():
    _, reasons = scorer.score({"sst_f": 80.0, "depth_ft": 400}, MAHI)
    assert any("in optimal 78–82°F band" in r for r in reasons)


def test_sst_far_outside_zero_subscore():
    # 60°F is >margin below the 78°F floor ⇒ SST subscore 0, phrased "outside".
    _, reasons = scorer.score({"sst_f": 60.0, "depth_ft": 400}, MAHI)
    assert any("outside optimal" in r for r in reasons)


def test_structure_overlap_ratio():
    _, reasons = scorer.score({"structure": ["current_edge", "reef_edge"]}, MAHI)
    assert any("Structure match: current_edge" in r for r in reasons)


def test_no_preferred_structure():
    _, reasons = scorer.score({"structure": ["reef"]}, MAHI)
    assert any("No preferred structure" in r for r in reasons)


def test_missing_features_drop_out_and_flag_confidence():
    # Only depth present: sst + structure missing ⇒ reduced-confidence note lists them.
    _, reasons = scorer.score({"depth_ft": 400}, MAHI)
    assert any("reduced confidence" in r and "sst" in r and "structure" in r for r in reasons)


def test_current_edge_affinity_zero_drops_component():
    profile = {**MAHI, "current_edge_affinity": 0}
    _, reasons = scorer.score(
        {"dist_to_stream_edge_nm": 1.0, "sst_f": 80, "depth_ft": 400}, profile
    )
    assert not any("current edge" in r for r in reasons)


def test_current_edge_present_when_affinity_nonzero():
    _, reasons = scorer.score({"dist_to_stream_edge_nm": 2.0, "sst_f": 80, "depth_ft": 400}, MAHI)
    assert any("2.0 nm from the current edge" in r for r in reasons)


def test_empty_features_no_crash():
    s, reasons = scorer.score({}, MAHI)
    assert s == 0.0
    assert reasons == ["no scorable features"]


def test_every_scored_result_has_reasons():
    s, reasons = scorer.score({"sst_f": 80, "depth_ft": 400, "structure": ["current_edge"]}, MAHI)
    assert 0 <= s <= 100
    assert reasons and all(isinstance(r, str) for r in reasons)


def test_pressure_component_only_for_falling_species():
    neutral = scorer.score({"pressure_trend_3h": -2.0, "sst_f": 80}, MAHI)[1]
    assert not any("pressure" in r for r in neutral)
    falling_profile = {**MAHI, "pressure_response": "falling"}
    falling = scorer.score({"pressure_trend_3h": -2.0, "sst_f": 80}, falling_profile)[1]
    assert any("Falling pressure" in r for r in falling)
