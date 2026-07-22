"""Moon illumination + a solunar activity proxy, computed locally (no feed, stdlib only).

Both are raw [0, 1] signals. The scorer (Phase 2) applies each species' moon_affinity /
solunar_weight; we do not weight here.
"""

import math
from datetime import date, datetime, timezone

# Reference new moon: 2000-01-06 18:14 UTC (standard epoch).
_NEW_MOON_EPOCH = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
SYNODIC_MONTH_DAYS = 29.53058867


def _parse(d: str | date) -> datetime:
    if isinstance(d, date):
        d = d.isoformat()
    # Evaluate at noon UTC of the given day.
    return datetime.fromisoformat(f"{d}T12:00:00+00:00")


def moon_phase_fraction(d: str | date) -> float:
    """Position in the synodic cycle: 0.0 = new, 0.5 = full, wraps at 1.0."""
    dt = _parse(d)
    days = (dt - _NEW_MOON_EPOCH).total_seconds() / 86400.0
    return (days % SYNODIC_MONTH_DAYS) / SYNODIC_MONTH_DAYS


def moon_illumination(d: str | date) -> float:
    """Illuminated fraction of the lunar disk, 0.0 (new) .. 1.0 (full)."""
    phase_angle = 2 * math.pi * moon_phase_fraction(d)
    return (1 - math.cos(phase_angle)) / 2


def solunar_score(d: str | date) -> float:
    """Coarse solunar activity proxy in [0, 1]: peaks at new and full moon (strongest
    feeding periods), troughs at the quarters. Distance to the nearest new/full point,
    normalized so a quarter moon scores 0."""
    f = moon_phase_fraction(d)
    dist_to_new_or_full = min(f, abs(f - 0.5), abs(f - 1.0))
    return max(0.0, 1.0 - dist_to_new_or_full / 0.25)
