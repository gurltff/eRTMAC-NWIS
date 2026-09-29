"""Map layers, the location detail panel, untapped spots, analytics and data-source info."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import current_user, require_roles
from ..config import REGION
from ..db import get_db
from ..services import ml, spatial
from ..services.location_intel import location_detail

router = APIRouter(prefix="/api", tags=["map"])


@router.get("/map/layers")
def layers(_: m.User = Depends(current_user), db: Session = Depends(get_db)):
    return {
        "region": REGION,
        "fields": [{k: f[k] for k in ("id", "name", "operator", "lat", "lon", "discovery_year", "reserves_mmbbl", "past_operators", "source")}
                   for f in spatial.get("fields", db)],
        "wells": [{"id": w.id, "name": w.name, "lat": w.lat, "lon": w.lon, "status": w.status, "outcome": w.outcome,
                   "is_active": w.is_active, "current_depth_m": w.current_depth_m, "operator": w.operator, "spud_year": w.spud_year,
                   "well_type": w.well_type, "bhl": [w.trajectory["bhl_lat"], w.trajectory["bhl_lon"]] if w.trajectory and w.trajectory.get("bhl_lat") else None,
                   "source": w.source}
                  for w in db.query(m.Well).all()],
        "zones": [{k: z[k] for k in ("id", "name", "zone_type", "legal_to_drill", "authority", "licensee", "polygon", "source")}
                  for z in spatial.get("zones", db)],
        "candidates": [{"id": c.id, "name": c.name, "lat": c.lat, "lon": c.lon, "target_formation": c.target_formation,
                        "planned_td_m": c.planned_td_m, "proposed_by": c.proposed_by, "status": c.status}
                       for c in db.query(m.CandidateLocation).all()],
        "landslides": spatial.get("landslides", db),
        "geology": [{k: g[k] for k in ("id", "name", "lithology", "rock_class", "polygon")} for g in spatial.get("geology", db)],
        "rivers": spatial.get("rivers", db),
    }


@router.get("/map/location")
def location(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
             _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    if not (REGION["min_lat"] - 0.5 <= lat <= REGION["max_lat"] + 0.5 and REGION["min_lon"] - 0.5 <= lon <= REGION["max_lon"] + 0.5):
        raise HTTPException(400, "Detailed checks cover Upper Assam and nearby only, where the sample data is. Use the Assam oil fields button to zoom in there.")
    return location_detail(db, lat, lon)


@router.get("/map/untapped")
def untapped(_: m.User = Depends(current_user)):
    models = ml.get_models()
    return {"spots": ml.untapped_spots(), "grid": models["grid"], "grid_step": ml.GRID_STEP, "explanation": ml.explain()}


@router.get("/ml/explain")
def explain(_: m.User = Depends(current_user)):
    return ml.explain()


@router.post("/ml/retrain")
def retrain(_: m.User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    spatial.refresh(db)
    ml.reset()
    ml.get_models(db)
    return ml.explain()


@router.get("/analytics/overview")
def overview(_: m.User = Depends(require_roles("admin", "engineer")), db: Session = Depends(get_db)):
    wells = db.query(m.Well).all()
    events = db.query(m.DrillingEvent).all()
    by_well = {w.id: w for w in wells}
    per_year = defaultdict(Counter)
    for e in events:
        if e.event_date:
            per_year[int(e.event_date[:4]) // 5 * 5][e.event_type] += 1
    npt_by_fm = defaultdict(float)
    count_by_fm_type = defaultdict(Counter)
    for e in events:
        npt_by_fm[e.formation or "Unknown"] += e.npt_hours or 0
        count_by_fm_type[e.formation or "Unknown"][e.event_type] += 1
    field_risk = defaultdict(lambda: {"wells": 0, "events": 0, "high": 0})
    for w in wells:
        key = w.field.name if w.field else "Exploration / other"
        field_risk[key]["wells"] += 1
    for e in events:
        w = by_well.get(e.well_id)
        key = w.field.name if w and w.field else "Exploration / other"
        field_risk[key]["events"] += 1
        field_risk[key]["high"] += e.severity == "high"
    week_ago = datetime.utcnow() - timedelta(days=7)
    drillers = db.query(m.DrillerProfile).all()
    return {
        "kpis": {
            "wells": len(wells),
            "active_wells": sum(w.is_active for w in wells),
            "events": len(events),
            "npt_hours": round(sum(e.npt_hours or 0 for e in events)),
            "drillers": len(drillers),
            "pending_approvals": sum(p.status == "submitted" for p in drillers),
            "open_alerts": db.query(m.WellAlert).filter(m.WellAlert.acknowledged.is_(False)).count(),
            "breaches_7d": db.query(m.BreachEvent).filter(m.BreachEvent.created_at >= week_ago,
                                                          m.BreachEvent.event_type.in_(["LEFT_ALLOWED_ZONE", "ENTERED_ILLEGAL_ZONE"])).count(),
        },
        "wells_by_status": Counter(w.status for w in wells),
        "wells_by_outcome": Counter(w.outcome for w in wells),
        "events_by_type": Counter(e.event_type for e in events),
        "events_by_period": [{"period": f"{y}–{y + 4}", **per_year[y]} for y in sorted(per_year)],
        "npt_by_formation": [{"formation": k, "npt_hours": round(v)} for k, v in sorted(npt_by_fm.items(), key=lambda x: -x[1])],
        "events_by_formation": [{"formation": k, **v} for k, v in count_by_fm_type.items()],
        "field_risk": sorted([{"field": k, **v, "events_per_well": round(v["events"] / max(1, v["wells"]), 1)}
                              for k, v in field_risk.items()], key=lambda x: -x["events_per_well"]),
        "drillers_by_status": Counter(p.status for p in drillers),
    }


@router.get("/meta/sources")
def sources(db: Session = Depends(get_db)):
    fields = spatial.get("fields", db)
    zones = spatial.get("zones", db)
    geology = spatial.get("geology", db)
    return {
        "notice": "This prototype runs on SAMPLE data. Field names, formations and protected areas are real names; "
                  "locations, outlines and all numbers are approximate or generated for the demo.",
        "datasets": [
            {"name": "Oil & gas fields", "used": fields[0]["source"] if fields else "-", "real_source": "Global Energy Monitor – Oil & Gas Extraction Tracker"},
            {"name": "Protected areas & forests", "used": ", ".join(sorted({z["source"] for z in zones if not z["legal_to_drill"]})),
             "real_source": "WDPA (protectedplanet.net) + OpenStreetMap / Geofabrik"},
            {"name": "Geology", "used": geology[0]["source"] if geology else "-", "real_source": "GSI Bhukosh"},
            {"name": "Landslides", "used": (spatial.get("landslides", db) or [{"source": "-"}])[0]["source"], "real_source": "NASA Global Landslide Catalog"},
            {"name": "Terrain & slope", "used": "Modelled terrain unless SRTM tiles are added", "real_source": "OpenTopography SRTM 30 m"},
            {"name": "Soil", "used": "ISRIC SoilGrids live (cached), estimate when offline", "real_source": "ISRIC SoilGrids v2.0"},
            {"name": "Drilling reports & events", "used": "Generated sample + Volve DDR-format sample", "real_source": "Equinor Volve / OIL DDRs & WCRs"},
            {"name": "Land ownership", "used": "Generated sample", "real_source": "Assam land records (Dharitree) – no open dataset"},
            {"name": "National data repository", "used": "Not connected", "real_source": "DGH National Data Repository (ndr.dghindia.gov.in)"},
        ],
    }
