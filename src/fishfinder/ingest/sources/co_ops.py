"""NOAA CO-OPS tides & currents (free, station-based).

Tides: hi/lo predictions at the nearest tide station → tide_state at the reference hour.
Currents: CO-OPS current stations are sparse offshore and the dominant offshore current
signal here is the Florida Current edge (dist_to_stream_edge_nm, from SST). We therefore
leave current_speed/dir null for the MVP; populate data/stations_coops.json with current
stations to wire them later.

https://api.tidesandcurrents.noaa.gov/api/prod/datagetter
"""

import json
from datetime import datetime, timezone

from ... import config, geo
from .. import http

NAME = "co_ops"

PREDICTIONS_URL = (
    "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    "?product=predictions&application=fishfinder"
    "&begin_date={ymd}&end_date={ymd}&datum=MLLW"
    "&station={station}&time_zone=gmt&units=english&interval=hilo&format=json"
)

NEAR_EVENT_MIN = 45  # within this many minutes of a hi/lo -> "high"/"low"


def _stations() -> list[dict]:
    return json.loads(config.COOPS_STATIONS_PATH.read_text())


def parse_events(payload: dict | None) -> list[tuple[datetime, str]]:
    """[(utc_datetime, 'H'|'L'), ...] from a CO-OPS predictions/hilo response."""
    if not payload or "predictions" not in payload:
        return []
    events = []
    for p in payload["predictions"]:
        try:
            dt = datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        events.append((dt, p.get("type", "")))
    events.sort(key=lambda e: e[0])
    return events


def tide_state_at(events: list[tuple[datetime, str]], ref: datetime) -> str | None:
    """rising | falling | high | low at ref, from surrounding hi/lo events."""
    if not events:
        return None
    for dt, typ in events:
        if abs((dt - ref).total_seconds()) <= NEAR_EVENT_MIN * 60:
            return "high" if typ == "H" else "low"
    before = [e for e in events if e[0] <= ref]
    after = [e for e in events if e[0] > ref]
    # Heading toward the next event: toward H => rising, toward L => falling.
    nxt = after[0] if after else before[-1]
    return "rising" if nxt[1] == "H" else "falling"


def fetch(zones: list[dict], date: str) -> dict[str, dict]:
    stations = _stations()
    if not stations:
        return {}
    ref = datetime.strptime(f"{date} 12:00", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    ymd = date.replace("-", "")

    cache: dict[str, list] = {}
    results: dict[str, dict] = {}
    for z in zones:
        station, _ = geo.nearest(z["lat"], z["lng"], stations)
        sid = station["id"]
        if sid not in cache:
            payload = http.get_json(PREDICTIONS_URL.format(ymd=ymd, station=sid))
            cache[sid] = parse_events(payload)
        state = tide_state_at(cache[sid], ref)
        if state is not None:
            results[z["zone_id"]] = {"tide_state": state}
    return results
