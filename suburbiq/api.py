"""FastAPI service behind the SuburbIQ web app.

The analytics live in `analytics.py` and are shared verbatim with the CLI — this
module only handles transport, filtering, and job orchestration. Ingest runs as a
background job because a cold Overpass fetch takes minutes and must not block a
request.
"""
import csv
import io
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import analytics, store
from .models import AREAS, CATEGORIES, SourceBlocked
from .normalise import SuburbResolver, normalise
from .paths import WEB_DIR, ensure
from .sources.osm import OSMAdapter, fetch_suburb_centroids
from .sources.yellowpages import YellowPagesAdapter

ADAPTERS = {"osm": OSMAdapter, "yellowpages": YellowPagesAdapter}

app = FastAPI(title="SuburbIQ API", version="1.0.0",
              description="Suburb-level market intelligence for Australian local business.")

# In-process job registry. Adequate for single-instance deployment; a multi-worker
# deployment would move this to Redis (see architecture.md §7).
JOBS: Dict[str, Dict] = {}
_lock = threading.Lock()


def _rows(category: str, source: str = "") -> List:
    conn = store.connect()
    try:
        return store.query(conn, category, source)
    finally:
        conn.close()


@app.get("/api/meta")
def meta():
    """Everything the frontend needs to build its controls."""
    conn = store.connect()
    try:
        loaded = [dict(r) for r in store.categories(conn)]
    finally:
        conn.close()
    return {
        "categories": sorted(CATEGORIES),
        "areas": [{"slug": a.slug, "label": a.label} for a in AREAS.values()],
        "sources": list(ADAPTERS),
        "loaded": loaded,
    }


@app.get("/api/analytics")
def get_analytics(category: str = Query(...), source: str = ""):
    rows = _rows(category, source)
    if not rows:
        raise HTTPException(404, f"no data for '{category}'. Ingest it first.")
    return {
        "category": category,
        "source": rows[0]["source"],
        "generated": max(r["ingested_at"] or "" for r in rows),
        "coverage": analytics.coverage(rows),
        "saturation": analytics.saturation(rows),
        "opportunity": analytics.opportunity(rows),
        "histogram": analytics.gap_histogram(rows),
    }


@app.get("/api/businesses")
def businesses(category: str = Query(...), q: str = "", suburb: str = "",
               min_gap: int = 0, source: str = "",
               limit: int = Query(50, le=500), offset: int = 0):
    """Filtered, paginated business list — the interactive leads table."""
    rows = _rows(category, source)
    if not rows:
        raise HTTPException(404, f"no data for '{category}'. Ingest it first.")

    needle = q.lower().strip()
    filtered = [
        r for r in rows
        if r["digital_gap_score"] >= min_gap
        and (not suburb or (r["suburb"] or "").lower() == suburb.lower())
        and (not needle or needle in (r["name"] or "").lower()
             or needle in (r["suburb"] or "").lower())
    ]
    page = filtered[offset:offset + limit]
    return {
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "items": [{
            "name": r["name"], "suburb": r["suburb"], "street": r["street"],
            "phone": r["phone"], "website": r["website"],
            "opening_hours": r["opening_hours"], "gap": r["digital_gap_score"],
        } for r in page],
    }


@app.get("/api/export.csv")
def export_csv(category: str = Query(...), min_gap: int = 0, source: str = ""):
    """Streamed CSV so a 100k-row export never buffers in memory."""
    rows = _rows(category, source)
    if not rows:
        raise HTTPException(404, f"no data for '{category}'.")
    leads = [L for L in analytics.leads(rows) if L["gap"] >= min_gap]

    def gen():
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["name", "suburb", "street", "phone",
                                            "website", "opening_hours", "gap"])
        w.writeheader()
        yield buf.getvalue()
        for row in leads:
            buf.seek(0), buf.truncate(0)
            w.writerow(row)
            yield buf.getvalue()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return StreamingResponse(gen(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="suburbiq-{category}-{stamp}.csv"'})


def _run_ingest(job_id: str, source: str, category: str, area_slug: str) -> None:
    """Background worker. Records terminal state on the job for polling."""
    def upd(**kw):
        with _lock:
            JOBS[job_id].update(**kw)

    try:
        area = AREAS[area_slug]
        adapter = ADAPTERS[source]()
        upd(status="fetching", message=f"querying {source}…")
        records = list(adapter.fetch(category, area))

        upd(status="normalising", message=f"{len(records)} records fetched",
            fetched=len(records))
        centroids = []
        if any(r.fields.get("lat") is not None for r in records):
            try:
                centroids = fetch_suburb_centroids(area)
            except Exception:
                pass  # source-provided suburbs still usable

        items, dropped = normalise(records, category, SuburbResolver(centroids))
        conn = store.connect()
        try:
            result = store.upsert(conn, items)
        finally:
            conn.close()
        upd(status="done", message=f"{result['inserted']} new, {result['updated']} updated",
            stored=result, dropped=dropped)

    except SourceBlocked as exc:
        upd(status="blocked", message=f"{exc.source} returned HTTP {exc.status}: {exc.detail}",
            remediation=exc.remediation)
    except Exception as exc:
        upd(status="error", message=str(exc))


@app.post("/api/ingest")
def start_ingest(background: BackgroundTasks, category: str = Query(...),
                 area: str = "sydney", source: str = "osm"):
    if category not in CATEGORIES:
        raise HTTPException(400, f"unknown category '{category}'")
    if area not in AREAS:
        raise HTTPException(400, f"unknown area '{area}'")
    if source not in ADAPTERS:
        raise HTTPException(400, f"unknown source '{source}'")

    job_id = uuid.uuid4().hex[:12]
    with _lock:
        JOBS[job_id] = {"id": job_id, "status": "queued", "message": "queued",
                        "category": category, "area": area, "source": source,
                        "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    background.add_task(_run_ingest, job_id, source, category, area)
    return {"job_id": job_id}


@app.get("/api/ingest/{job_id}")
def ingest_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return job


@app.get("/health")
def health():
    return {"ok": True}


ensure()
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
