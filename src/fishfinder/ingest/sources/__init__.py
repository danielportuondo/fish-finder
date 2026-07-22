"""Feed sources. Each module exposes NAME and fetch(zones, date) -> {zone_id: {col: val}}
and must never raise (return {} on failure). run.py iterates SOURCES in order."""

from . import co_ops, coastwatch, ndbc, open_meteo

SOURCES = [open_meteo, coastwatch, co_ops, ndbc]

__all__ = ["SOURCES", "open_meteo", "coastwatch", "co_ops", "ndbc"]
