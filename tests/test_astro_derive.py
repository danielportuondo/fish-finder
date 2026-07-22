import pytest

from fishfinder.ingest import astro, derive


# --- astro ---------------------------------------------------------------


def test_moon_illumination_full_and_new():
    # 2000-01-06 was ~new moon (epoch); ~14.7 days later is ~full.
    assert astro.moon_illumination("2000-01-06") < 0.05
    assert astro.moon_illumination("2000-01-21") > 0.9


def test_moon_illumination_in_range():
    for d in ["2026-07-22", "2026-01-01", "2026-12-31"]:
        assert 0.0 <= astro.moon_illumination(d) <= 1.0


def test_solunar_peaks_at_new_and_full():
    new = astro.solunar_score("2000-01-06")
    quarter = astro.solunar_score("2000-01-14")  # ~first quarter
    assert new > 0.9
    assert quarter < 0.2
    assert 0.0 <= quarter <= 1.0


# --- derive --------------------------------------------------------------


def test_pressure_trend_basic():
    series = [1015.0, 1015.5, 1016.0, 1016.8, 1017.0]
    assert derive.pressure_trend_3h(series, 3) == pytest.approx(1.8)


def test_pressure_trend_missing_and_bounds():
    assert derive.pressure_trend_3h([None, 1015.5, 1016.0, 1017.0], 3) is None  # endpoint missing
    assert derive.pressure_trend_3h([1015.0, 1016.0], 3) is None  # idx out of range
    assert derive.pressure_trend_3h([1015.0, 1016.0, 1017.0, 1018.0], 2) is None  # idx<3


def test_sst_break_gradient():
    # center 79, hottest neighbor 80.5 => 1.5°F over 2 nm = 0.75 °F/nm
    assert derive.sst_break_gradient(79.0, [79.2, 80.5, None, 78.8], 2.0) == pytest.approx(0.75)
    assert derive.sst_break_gradient(None, [80.0], 2.0) is None
    assert derive.sst_break_gradient(79.0, [None, None], 2.0) is None


def test_dist_to_stream_edge():
    # steepest step is between 6 and 9 nm (78->82), midpoint 7.5
    transect = [(0.0, 77.0), (3.0, 77.5), (6.0, 78.0), (9.0, 82.0), (12.0, 82.5)]
    assert derive.dist_to_stream_edge_nm(transect) == pytest.approx(7.5)
    assert derive.dist_to_stream_edge_nm([(0.0, 77.0)]) is None
    assert derive.dist_to_stream_edge_nm([(0.0, None), (3.0, None)]) is None
