"""NOAA CoastWatch / NASA Ocean Color via ERDDAP griddap (free, no key).

SST: JPL MUR (jplMURSST41, ~1 km, 1-day lag) — one small box per zone yields the center
value, a local break gradient, and an eastward transect for the Florida Current edge.
Chlorophyll: NOAA S-NPP VIIRS Science-Quality global daily — one point per zone; cloudy
pixels return null (expected per HANDOFF §7).
"""

from ... import geo
from .. import derive, http

NAME = "coastwatch"

SST_URL = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.json"
    "?analysed_sst%5B(last)%5D"
    "%5B({lat_min}):3:({lat_max})%5D"
    "%5B({lng_min}):3:({lng_max})%5D"
)
CHL_URL = (
    "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSSQchlaDaily.json"
    "?chlor_a%5B(last)%5D%5B(0.0)%5D%5B({lat})%5D%5B({lng})%5D"
)

# Box: ~3.6 nm north/south, extends east toward the Gulf Stream to catch the edge.
BOX_LAT_PAD = 0.06
BOX_LNG_WEST = 0.06
BOX_LNG_EAST = 0.45


def _rows(payload: dict | None) -> list[list]:
    """Rows from an ERDDAP griddap .json, or [] (ERDDAP errors have no 'table')."""
    if not payload or "table" not in payload:
        return []
    return payload["table"].get("rows", [])


def _c_to_f(c):
    return c * 9 / 5 + 32 if c is not None else None


def parse_sst_box(payload: dict | None, zone: dict) -> dict:
    """From an SST box, derive sst_f (nearest cell), sst_break_gradient (nearest
    neighbors), and dist_to_stream_edge_nm (steepest front on the eastward transect)."""
    cells = [(lat, lng, sst) for _, lat, lng, sst in _rows(payload) if sst is not None]
    if not cells:
        return {}
    zlat, zlng = zone["lat"], zone["lng"]
    cells.sort(key=lambda c: geo.haversine_nm(zlat, zlng, c[0], c[1]))
    clat, clng, csst = cells[0]
    center_f = _c_to_f(csst)
    out = {"sst_f": round(center_f, 2)}

    neighbors = cells[1:5]
    if neighbors:
        spacing = geo.haversine_nm(clat, clng, neighbors[0][0], neighbors[0][1])
        grad = derive.sst_break_gradient(center_f, [_c_to_f(n[2]) for n in neighbors], spacing)
        if grad is not None:
            out["sst_break_gradient"] = grad

    # Eastward transect at (nearest to) the center latitude: monotonic in distance.
    lat_tol = BOX_LAT_PAD / 2
    transect = [
        (geo.haversine_nm(zlat, zlng, lat, lng), _c_to_f(sst))
        for lat, lng, sst in cells
        if abs(lat - clat) <= lat_tol and lng >= zlng
    ]
    edge = derive.dist_to_stream_edge_nm(transect)
    if edge is not None:
        out["dist_to_stream_edge_nm"] = edge
    return out


def parse_chl(payload: dict | None) -> dict:
    rows = _rows(payload)
    if not rows:
        return {}
    val = rows[-1][-1]  # chlor_a is the last column
    return {} if val is None else {"chlorophyll": round(val, 4)}


def fetch(zones: list[dict], date: str) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for z in zones:
        box = http.get_json(
            SST_URL.format(
                lat_min=z["lat"] - BOX_LAT_PAD,
                lat_max=z["lat"] + BOX_LAT_PAD,
                lng_min=z["lng"] - BOX_LNG_WEST,
                lng_max=z["lng"] + BOX_LNG_EAST,
            )
        )
        chl = http.get_json(CHL_URL.format(lat=z["lat"], lng=z["lng"]))
        feat = {**parse_sst_box(box, z), **parse_chl(chl)}
        if feat:
            results[z["zone_id"]] = feat
    return results
