"""NDBC buoy real-time observations (free, fixed-width text). Cross-check / fallback for
wind, wave height, and water temp where Open-Meteo has gaps; run.py precedence puts NDBC
last for those columns.

https://www.ndbc.noaa.gov/data/realtime2/<STATION>.txt
"""

import json

from ... import config, geo
from .. import http

NAME = "ndbc"

REALTIME_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

MS_TO_KT = 1.943844
M_TO_FT = 3.28084
MISSING = "MM"


def _stations() -> list[dict]:
    return json.loads(config.NDBC_STATIONS_PATH.read_text())


def _num(token: str | None):
    if token is None or token == MISSING:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def parse_realtime(text: str | None) -> dict:
    """Most recent observation row → wind/wave/water-temp features."""
    if not text:
        return {}
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3 or not lines[0].startswith("#"):
        return {}
    cols = lines[0].lstrip("#").split()
    # First non-header line is the most recent observation.
    data_line = next((ln for ln in lines if not ln.startswith("#")), None)
    if data_line is None:
        return {}
    values = data_line.split()
    if len(values) != len(cols):
        return {}
    row = dict(zip(cols, values))

    out = {}
    wspd = _num(row.get("WSPD"))
    if wspd is not None:
        out["wind_speed_kt"] = round(wspd * MS_TO_KT, 2)
    wdir = _num(row.get("WDIR"))
    if wdir is not None:
        out["wind_dir_deg"] = wdir
    wvht = _num(row.get("WVHT"))
    if wvht is not None:
        out["wave_height_ft"] = round(wvht * M_TO_FT, 2)
    wtmp = _num(row.get("WTMP"))
    if wtmp is not None:
        out["sst_f"] = round(wtmp * 9 / 5 + 32, 2)
    return out


def fetch(zones: list[dict], date: str) -> dict[str, dict]:
    stations = _stations()
    if not stations:
        return {}
    cache: dict[str, dict] = {}
    results: dict[str, dict] = {}
    for z in zones:
        station, _ = geo.nearest(z["lat"], z["lng"], stations)
        sid = station["id"]
        if sid not in cache:
            cache[sid] = parse_realtime(http.get_text(REALTIME_URL.format(station=sid)))
        if cache[sid]:
            results[z["zone_id"]] = dict(cache[sid])
    return results
