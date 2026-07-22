# References & Tools Log

Living log of every dependency, data feed, external API, dataset, library, and notable
reference. **Update in the same commit** whenever one is introduced (see `docs/HANDOFF.md` §12).

| Date added | Name | Type | Used for | Link |
|------------|------|------|----------|------|
| 2026-07-22 | Python 3.12+ | tool | ingestion, scoring, server | https://www.python.org/ |
| 2026-07-22 | uv | tool | environment & dependency management | https://docs.astral.sh/uv/ |
| 2026-07-22 | ruff | lib | lint + format | https://docs.astral.sh/ruff/ |
| 2026-07-22 | pytest | lib | tests | https://docs.pytest.org/ |
| 2026-07-22 | SQLite (stdlib `sqlite3`) | tool | local data store (zone_conditions, catch_logs, trips, species, profiles) | https://docs.python.org/3/library/sqlite3.html |
| 2026-07-22 | GeoJSON (RFC 7946) | doc | zone catalog file format (`data/zones.geojson`) | https://datatracker.ietf.org/doc/html/rfc7946 |
| 2026-07-22 | GEBCO / NOAA bathymetry | dataset | source for zone depths/coordinates (used once to build the catalog) | https://www.gebco.net/ |

<!--
Environmental data feeds (HANDOFF §7) are added here in Phase 1 as each is wired in:
NOAA CoastWatch / NASA Ocean Color (SST + chlorophyll), NOAA CO-OPS (tides/currents),
NDBC buoys, Open-Meteo Marine (waves/wind/SST).
-->
