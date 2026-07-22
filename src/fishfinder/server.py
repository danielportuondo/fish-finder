"""FastAPI adapter for the recommendation + catch-logging pipeline (HANDOFF §8, §6).

The scorer, recommendation, and catch-logging cores stay framework-agnostic; FastAPI lives only in
this file. Serves the bare-bones web UI at / (same origin, no CORS). Run with:

  uv run uvicorn fishfinder.server:app --reload
"""

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import catchlog, config, db, recommend

app = FastAPI(title="fish-finder recommendations")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.WEB_DIR / "index.html")


@app.get("/meta")
def meta() -> dict:
    """Ports + species for the UI dropdowns — kept data-driven, never hardcoded in the client."""
    conn = db.connect(config.DB_PATH)
    try:
        ports = [
            {"code": r["code"], "name": r["name"]}
            for r in conn.execute("SELECT code, name FROM ports ORDER BY name")
        ]
        species = [
            {"code": r["code"], "display_name": r["display_name"]}
            for r in conn.execute("SELECT code, display_name FROM species ORDER BY display_name")
        ]
        return {"ports": ports, "species": species}
    finally:
        conn.close()


@app.get("/recommendations")
def recommendations(
    port: str = Query(..., description="launch point code, e.g. haulover"),
    range_nm: float = Query(..., gt=0, description="how far the boat will run, nautical miles"),
    species: str = Query(..., description="target species code, e.g. mahi"),
    date: str | None = Query(None, description="YYYY-MM-DD; defaults to today (UTC)"),
    top_n: int = Query(10, gt=0),
) -> dict:
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = db.connect(config.DB_PATH)
    try:
        return recommend.recommend(conn, port, range_nm, species, date, top_n)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


class CatchIn(BaseModel):
    device_id: str
    zone_id: str
    date: str  # YYYY-MM-DD; resolves the conditions snapshot
    species: str | None = None  # code; None only for a skunked/negative log
    count: int | None = None
    notes: str | None = None
    outcome: str = "caught"


@app.post("/catch")
def log_catch(body: CatchIn) -> dict:
    conn = db.connect(config.DB_PATH)
    try:
        return catchlog.log_catch(
            conn,
            device_id=body.device_id,
            zone_id=body.zone_id,
            date=body.date,
            species=body.species,
            count=body.count,
            notes=body.notes,
            outcome=body.outcome,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


class TripZone(BaseModel):
    zone_id: str
    outcome: str = "caught"
    species: str | None = None  # code; None only for a skunked/negative zone
    count: int | None = None
    notes: str | None = None


class TripIn(BaseModel):
    device_id: str
    port: str  # launch point code
    range_nm: float
    target_species: list[str]
    date: str  # YYYY-MM-DD; resolves each zone's conditions snapshot
    zones: list[TripZone]


@app.post("/trip")
def log_trip(body: TripIn) -> dict:
    conn = db.connect(config.DB_PATH)
    try:
        return catchlog.log_trip(
            conn,
            device_id=body.device_id,
            port=body.port,
            range_nm=body.range_nm,
            target_species=body.target_species,
            date=body.date,
            zones=[z.model_dump() for z in body.zones],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()
