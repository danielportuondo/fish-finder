"""Source-parser tests. Payloads mirror the real feed shapes verified at build time; no
network is touched (parse_* functions are pure)."""

from datetime import datetime, timezone

from fishfinder.ingest.sources import co_ops, coastwatch, ndbc, open_meteo

DATE = "2026-07-22"


# --- Open-Meteo ----------------------------------------------------------


def _hourly(**series):
    times = [f"{DATE}T{h:02d}:00" for h in range(24)]
    return {"hourly": {"time": times, **series}}


def test_open_meteo_marine_parse():
    payload = _hourly(
        wave_height=[0.5] * 24,
        sea_surface_temperature=[30.0] * 24,
    )
    out = open_meteo.parse_marine(payload, DATE)
    assert out["wave_height_ft"] == round(0.5 * 3.28084, 2)
    assert out["sst_f"] == 86.0  # 30C


def test_open_meteo_forecast_parse_with_trend():
    pressures = [1010.0 + i for i in range(24)]  # +1 mb/hr
    payload = _hourly(
        surface_pressure=pressures,
        wind_speed_10m=[20.0] * 24,
        wind_direction_10m=[120] * 24,
    )
    out = open_meteo.parse_forecast(payload, DATE)
    assert out["wind_speed_kt"] == round(20.0 * 0.539957, 2)
    assert out["wind_dir_deg"] == 120
    assert out["pressure_mb"] == 1022.0  # index 12
    assert out["pressure_trend_3h"] == 3.0  # 1022 - 1019


def test_open_meteo_empty_payload():
    assert open_meteo.parse_marine(None, DATE) == {}
    assert open_meteo.parse_forecast({}, DATE) == {}


# --- CoastWatch ----------------------------------------------------------


def _sst_box(rows):
    return {
        "table": {"columnNames": ["time", "latitude", "longitude", "analysed_sst"], "rows": rows}
    }


def test_coastwatch_sst_box_center_and_gradient():
    zone = {"lat": 25.91, "lng": -80.04}
    rows = [
        ["t", 25.91, -80.04, 25.0],  # center
        ["t", 25.94, -80.04, 26.0],  # ~1.8 nm north, warmer
        ["t", 25.91, -80.01, 25.5],  # east
    ]
    out = coastwatch.parse_sst_box(_sst_box(rows), zone)
    assert out["sst_f"] == 77.0  # 25C
    assert out["sst_break_gradient"] > 0  # a warm neighbor exists


def test_coastwatch_sst_box_all_null():
    zone = {"lat": 25.91, "lng": -80.04}
    assert coastwatch.parse_sst_box(_sst_box([["t", 25.91, -80.04, None]]), zone) == {}
    assert coastwatch.parse_sst_box(None, zone) == {}


def test_coastwatch_chl_parse():
    ok = {"table": {"rows": [["2026-07-20T12:00:00Z", 0, 25.9, -80.04, 0.18]]}}
    assert coastwatch.parse_chl(ok) == {"chlorophyll": 0.18}
    null = {"table": {"rows": [["2026-07-20T12:00:00Z", 0, 25.9, -80.04, None]]}}
    assert coastwatch.parse_chl(null) == {}
    # ERDDAP error response has no 'table'
    assert coastwatch.parse_chl({"code": 404}) == {}


# --- CO-OPS --------------------------------------------------------------

COOPS_PAYLOAD = {
    "predictions": [
        {"t": "2026-07-22 01:38", "v": "0.305", "type": "L"},
        {"t": "2026-07-22 07:41", "v": "1.836", "type": "H"},
        {"t": "2026-07-22 14:08", "v": "0.023", "type": "L"},
        {"t": "2026-07-22 20:30", "v": "1.835", "type": "H"},
    ]
}


def test_coops_tide_state_transitions():
    events = co_ops.parse_events(COOPS_PAYLOAD)
    assert len(events) == 4
    # 12:00 is between H(07:41) and L(14:08) -> falling
    ref = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    assert co_ops.tide_state_at(events, ref) == "falling"
    # 03:00 is between L(01:38) and H(07:41) -> rising
    assert (
        co_ops.tide_state_at(events, datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc)) == "rising"
    )
    # near 07:41 -> high
    assert co_ops.tide_state_at(events, datetime(2026, 7, 22, 7, 50, tzinfo=timezone.utc)) == "high"


def test_coops_empty():
    assert co_ops.parse_events(None) == []
    assert co_ops.tide_state_at([], datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)) is None


# --- NDBC ----------------------------------------------------------------

NDBC_TEXT = (
    "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE\n"
    "#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft\n"
    "2026 07 22 17 30 100  7.0  9.0   1.3     8   4.9 132 1020.0  29.1  30.3  24.8   MM   MM    MM\n"
    "2026 07 22 17 20 100  8.0  9.0   1.3     8   4.9 132 1020.1  29.2  30.3  24.2   MM   MM    MM\n"
)


def test_ndbc_parse_latest_row():
    out = ndbc.parse_realtime(NDBC_TEXT)
    assert out["wind_speed_kt"] == round(7.0 * 1.943844, 2)
    assert out["wind_dir_deg"] == 100.0
    assert out["wave_height_ft"] == round(1.3 * 3.28084, 2)
    assert out["sst_f"] == round(30.3 * 9 / 5 + 32, 2)


def test_ndbc_missing_values_and_empty():
    text = (
        "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE\n"
        "#units\n"
        "2026 07 22 17 30 140  5.1  6.7    MM    MM    MM  MM 1017.1  30.1    MM    MM   MM   MM    MM\n"
    )
    out = ndbc.parse_realtime(text)
    assert "wave_height_ft" not in out  # WVHT was MM
    assert "sst_f" not in out  # WTMP was MM
    assert out["wind_speed_kt"] == round(5.1 * 1.943844, 2)
    assert ndbc.parse_realtime(None) == {}
    assert ndbc.parse_realtime("") == {}
