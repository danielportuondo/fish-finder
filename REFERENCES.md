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
| 2026-07-22 | Open-Meteo Marine API | data feed | wave height/direction + SST fallback per zone (no key) | https://open-meteo.com/en/docs/marine-weather-api |
| 2026-07-22 | Open-Meteo Forecast API | data feed | surface pressure (+3h trend), wind speed/direction per zone (no key) | https://open-meteo.com/en/docs |
| 2026-07-22 | Open-Meteo Historical Weather API (ERA5 archive) | data feed | historical pressure/wind for report backfill; `start_date`/`end_date`, no key | https://open-meteo.com/en/docs/historical-weather-api |
| 2026-07-22 | Open-Meteo Marine API (historical range) | data feed | historical wave height + SST for report backfill (`start_date`/`end_date` reanalysis; same endpoint as the live Marine row) | https://open-meteo.com/en/docs/marine-weather-api |
| 2026-07-22 | NOAA CoastWatch ERDDAP — JPL MUR SST (jplMURSST41) | data feed | sea-surface temp, break gradient, Florida Current edge distance; time-indexed `[(date)]` selector reused for historical backfill | https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.html |
| 2026-07-22 | NOAA CoastWatch ERDDAP — S-NPP VIIRS chlorophyll (noaacwNPPVIIRSSQchlaDaily) | data feed | chlorophyll-a per zone (cloud gaps expected); time-indexed `[(date)]` selector reused for historical backfill | https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSSQchlaDaily.html |
| 2026-07-22 | NOAA CO-OPS Tides & Currents API | API | hi/lo tide predictions → tide_state (nearest station) | https://api.tidesandcurrents.noaa.gov/api/prod/ |
| 2026-07-22 | NDBC buoy real-time data | data feed | observed wind/wave/water-temp fallback (nearest buoy) | https://www.ndbc.noaa.gov/ |
| 2026-07-22 | FastAPI | lib | HTTP layer for GET /recommendations (optional `serve` extra) | https://fastapi.tiangolo.com/ |
| 2026-07-22 | uvicorn | lib | ASGI server running the FastAPI app (optional `serve` extra) | https://www.uvicorn.org/ |
| 2026-07-23 | Logistic regression (pure-Python, no dep) | doc | Phase 5 per-species learned scorer; standardized + L2-regularized, hot-swaps the rule scorer via the shared `score()` contract | https://en.wikipedia.org/wiki/Logistic_regression |
