"""Rule-based zone scorer.

Design invariant (HANDOFF §2/§13): ``score(features, profile) -> (score, reasons)`` is a pure
function. The rule engine and any future ML model share this signature so they are hot-swappable
per species without touching the recommendation pipeline.

Species magnitudes come entirely from ``species_profiles.params`` (the ``profile`` arg); this
module never hardcodes species logic. Only general engine calibration — tolerance margins and
base dimension weights — lives here, and those are overridable per profile via ``profile["weights"]``.

Each component yields a sub-score in [0, 1] and a weight. A component whose required feature is
missing (None) drops out of both the numerator and the denominator, so we score with whatever
resolved and never crash on gaps (HANDOFF §7).
"""

# Engine calibration (not species logic). Overridable via profile["weights"].
BASE_WEIGHTS = {
    "sst": 1.0,
    "depth": 0.8,
    "structure": 0.8,
    "chlorophyll": 0.5,
    "pressure": 0.5,
    "weedline": 0.3,
}
SST_MARGIN_F = 4.0
DEPTH_MARGIN_FRAC = 0.5  # decay margin as a fraction of the band width
CURRENT_EDGE_DECAY_NM = 15.0
CHL_BLUE_MAX = 0.15  # mg/m^3; below this is clean bluewater
CHL_BLUE_SPAN = 0.35
CHL_MIXED_RANGE = (0.15, 1.0)
CHL_MIXED_SPAN = 0.5
GRAD_STRONG = 1.0  # °F/nm SST gradient that reads as a strong break
CORE_DIMS = ("sst", "depth", "structure")


def _band_fit(value: float, lo: float, hi: float, margin: float) -> float:
    """1.0 inside [lo, hi], linear decay to 0 over ``margin`` outside it."""
    if lo <= value <= hi:
        return 1.0
    dist = lo - value if value < lo else value - hi
    return max(0.0, 1.0 - dist / margin) if margin > 0 else 0.0


def _fmt_range(lo: float, hi: float) -> str:
    return f"{lo:g}–{hi:g}"


def _sst(features, profile):
    sst, band = features.get("sst_f"), profile.get("sst_optimal_f")
    if sst is None or not band:
        return None
    lo, hi = band
    s = _band_fit(sst, lo, hi, SST_MARGIN_F)
    where = "in" if s == 1.0 else ("near" if s > 0 else "outside")
    return s, "sst", f"SST {sst:.1f}°F {where} optimal {_fmt_range(lo, hi)}°F band"


def _depth(features, profile):
    depth, band = features.get("depth_ft"), profile.get("depth_ft")
    if depth is None or not band:
        return None
    lo, hi = band
    s = _band_fit(depth, lo, hi, (hi - lo) * DEPTH_MARGIN_FRAC)
    where = "within" if s == 1.0 else ("near" if s > 0 else "outside")
    return s, "depth", f"Depth {depth:g} ft {where} {_fmt_range(lo, hi)} ft range"


def _structure(features, profile):
    prefers = profile.get("prefers_structure") or []
    zone = features.get("structure")
    if zone is None or not prefers:
        return None
    matched = [s for s in prefers if s in zone]
    subscore = len(matched) / len(prefers)
    if matched:
        return subscore, "structure", f"Structure match: {', '.join(matched)}"
    return 0.0, "structure", f"No preferred structure (wants {', '.join(prefers)})"


def _current_edge(features, profile):
    affinity = profile.get("current_edge_affinity")
    dist = features.get("dist_to_stream_edge_nm")
    if not affinity or dist is None:  # affinity 0 or missing ⇒ component drops out
        return None
    subscore = max(0.0, 1.0 - dist / CURRENT_EDGE_DECAY_NM)
    return subscore, ("current_edge", affinity), f"{dist:.1f} nm from the current edge"


def _chlorophyll(features, profile):
    pref = profile.get("chlorophyll_pref")
    chl = features.get("chlorophyll")
    grad = features.get("sst_break_gradient")
    if pref == "break":
        if grad is None:
            return None
        subscore = min(grad / GRAD_STRONG, 1.0)
        return subscore, "chlorophyll", f"SST break {grad:.2f}°F/nm (frontal edge)"
    if chl is None:
        return None
    if pref == "blue":
        subscore = max(0.0, 1.0 - max(0.0, chl - CHL_BLUE_MAX) / CHL_BLUE_SPAN)
        return subscore, "chlorophyll", f"Clean blue water (chl {chl:.2f})"
    if pref == "mixed":
        lo, hi = CHL_MIXED_RANGE
        subscore = _band_fit(chl, lo, hi, CHL_MIXED_SPAN)
        return subscore, "chlorophyll", f"Green/mixed water (chl {chl:.2f})"
    return None


def _pressure(features, profile):
    # Only "falling" species care; a neutral response leaves the component inert.
    if profile.get("pressure_response") != "falling":
        return None
    trend = features.get("pressure_trend_3h")
    if trend is None:
        return None
    subscore = max(0.0, min(1.0, -trend / 2.0))  # ~2 mb/3h fall ⇒ full credit
    verb = "Falling" if trend < 0 else "Rising"
    return subscore, "pressure", f"{verb} pressure ({trend:+.1f} mb/3h)"


def _solunar(features, profile):
    weight = profile.get("solunar_weight")
    score = features.get("solunar_score")
    if not weight or score is None:
        return None
    return score, ("solunar", weight), f"Solunar score {score:.2f}"


def _moon(features, profile):
    affinity = profile.get("moon_affinity")
    illum = features.get("moon_illumination")
    if not affinity or illum is None:
        return None
    return illum, ("moon", affinity), f"Moon {illum:.0%} illuminated"


def _weedline(features, profile):
    # Dormant until a weedline signal exists in the data; honest no-op for now.
    if not profile.get("weedline_bonus"):
        return None
    if "weedline" not in (features.get("structure") or []):
        return None
    return 1.0, "weedline", "Weedline present"


_COMPONENTS = (
    _sst,
    _depth,
    _structure,
    _current_edge,
    _chlorophyll,
    _pressure,
    _solunar,
    _moon,
    _weedline,
)


def score(features: dict, profile: dict) -> tuple[float, list[str]]:
    """Score one (zone, species) pair. Returns (0–100 score, human-readable reasons)."""
    weights = {**BASE_WEIGHTS, **(profile.get("weights") or {})}
    total_w = 0.0
    weighted = 0.0
    reasons: list[str] = []
    present_core: set[str] = set()

    for component in _COMPONENTS:
        result = component(features, profile)
        if result is None:
            continue
        subscore, key, reason = result
        # Affinity-driven dims carry their own weight as (name, weight); others use BASE_WEIGHTS.
        name, weight = key if isinstance(key, tuple) else (key, weights.get(key, 0.0))
        if weight <= 0:
            continue
        total_w += weight
        weighted += weight * subscore
        reasons.append(reason)
        if name in CORE_DIMS:
            present_core.add(name)

    missing_core = [d for d in CORE_DIMS if d not in present_core]
    if missing_core:
        reasons.append(f"reduced confidence: no {'/'.join(missing_core)}")

    if total_w == 0:
        return 0.0, ["no scorable features"]
    return round(weighted / total_w * 100, 1), reasons
