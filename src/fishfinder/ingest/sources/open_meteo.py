"""Open-Meteo Marine + Forecast (free, no key). The backbone feed: wave/wind/pressure
plus an SST fallback. Pure lat/lng — one request each per zone.

Marine:   https://marine-api.open-meteo.com/v1/marine
Forecast: https://api.open-meteo.com/v1/forecast
"""

from .. import derive, http

NAME = "open_meteo"

MARINE_URL = (
    "https://marine-api.open-meteo.com/v1/marine"
    "?latitude={lat}&longitude={lng}"
    "&hourly=wave_height,wave_direction,sea_surface_temperature"
    "&forecast_days=1&timezone=UTC"
)
FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lng}"
    "&hourly=surface_pressure,wind_speed_10m,wind_direction_10m"
    "&forecast_days=1&timezone=UTC"
)

KMH_TO_KT = 0.539957
M_TO_FT = 3.28084


def _hour_index(times: list[str], date: str) -> int | None:
    """Index of the representative hour (12:00 UTC) in the hourly time array."""
    if not times:
        return None
    target = f"{date}T12:00"
    try:
        return times.index(target)
    except ValueError:
        return min(12, len(times) - 1)


def _at(series, idx):
    if not series or idx is None or not (0 <= idx < len(series)):
        return None
    return series[idx]


def _c_to_f(c):
    return round(c * 9 / 5 + 32, 2) if c is not None else None


def parse_marine(payload: dict | None, date: str) -> dict:
    if not payload or "hourly" not in payload:
        return {}
    h = payload["hourly"]
    idx = _hour_index(h.get("time", []), date)
    out = {}
    wave = _at(h.get("wave_height"), idx)
    if wave is not None:
        out["wave_height_ft"] = round(wave * M_TO_FT, 2)
    sst = _c_to_f(_at(h.get("sea_surface_temperature"), idx))
    if sst is not None:
        out["sst_f"] = sst
    return out


def parse_forecast(payload: dict | None, date: str) -> dict:
    if not payload or "hourly" not in payload:
        return {}
    h = payload["hourly"]
    times = h.get("time", [])
    idx = _hour_index(times, date)
    out = {}
    wind = _at(h.get("wind_speed_10m"), idx)
    if wind is not None:
        out["wind_speed_kt"] = round(wind * KMH_TO_KT, 2)
    wdir = _at(h.get("wind_direction_10m"), idx)
    if wdir is not None:
        out["wind_dir_deg"] = wdir
    pressures = h.get("surface_pressure") or []
    p = _at(pressures, idx)
    if p is not None:
        out["pressure_mb"] = p
    if idx is not None:
        trend = derive.pressure_trend_3h(pressures, idx)
        if trend is not None:
            out["pressure_trend_3h"] = trend
    return out


def fetch(zones: list[dict], date: str) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for z in zones:
        marine = http.get_json(MARINE_URL.format(lat=z["lat"], lng=z["lng"]))
        forecast = http.get_json(FORECAST_URL.format(lat=z["lat"], lng=z["lng"]))
        feat = {**parse_marine(marine, date), **parse_forecast(forecast, date)}
        if feat:
            results[z["zone_id"]] = feat
    return results
