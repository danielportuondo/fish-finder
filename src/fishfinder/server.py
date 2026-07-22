"""FastAPI adapter for the recommendation pipeline (HANDOFF §8).

The scorer and pipeline stay framework-agnostic; FastAPI lives only in this file. Run with:

  uv run uvicorn fishfinder.server:app --reload
"""

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query

from . import config, db, recommend

app = FastAPI(title="fish-finder recommendations")


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
