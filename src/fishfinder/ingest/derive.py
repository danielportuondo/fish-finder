"""Derived features computed from raw feed values. Each returns None when inputs are
missing so a gap propagates cleanly instead of raising (HANDOFF §7)."""


def pressure_trend_3h(series: list[float | None], idx: int) -> float | None:
    """Change in surface pressure (mb) over the 3 hours ending at `idx` in an hourly
    series: series[idx] - series[idx-3]. None if either endpoint is missing."""
    if idx < 3 or idx >= len(series):
        return None
    now, past = series[idx], series[idx - 3]
    if now is None or past is None:
        return None
    return round(now - past, 2)


def sst_break_gradient(
    center: float | None, neighbors: list[float | None], spacing_nm: float
) -> float | None:
    """Steepest SST change (°F per nm) between the zone and its neighbor samples.
    None if the center or all neighbors are missing, or spacing is non-positive."""
    if center is None or spacing_nm <= 0:
        return None
    diffs = [abs(n - center) for n in neighbors if n is not None]
    if not diffs:
        return None
    return round(max(diffs) / spacing_nm, 3)


def dist_to_stream_edge_nm(transect: list[tuple[float, float | None]]) -> float | None:
    """Coarse distance (nm) from the zone to the Florida Current edge, approximated as the
    location of the steepest SST front along an offshore transect.

    `transect` is [(dist_nm_from_zone, sst_f), ...] sampled outward. Returns the midpoint
    distance of the steepest adjacent SST step. None if fewer than 2 valid samples.

    This is deliberately coarse (a real derivation needs altimetry/frontal analysis); it is
    flagged coarse in source_meta and nulls are acceptable.
    """
    pts = [(d, s) for d, s in transect if s is not None]
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p[0])
    best_dist, best_grad = None, -1.0
    for (d0, s0), (d1, s1) in zip(pts, pts[1:]):
        span = d1 - d0
        if span <= 0:
            continue
        grad = abs(s1 - s0) / span
        if grad > best_grad:
            best_grad, best_dist = grad, (d0 + d1) / 2
    return None if best_dist is None else round(best_dist, 2)
